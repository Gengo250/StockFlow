from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.infrastructure.repositories.supabase_sale_repository import (
    SupabaseSaleRepository,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "database/supabase/migrations/20261016120000_atomic_multi_item_sales.sql"
)
TABLES = ROOT / "database/code/tables/06_clients_sales.sql"
PROCEDURES = ROOT / "database/code/procedures/07_clients_sales.sql"
COMPLETION = ROOT / "database/code/triggers/06_sale_completion.sql"


def test_migration_adds_snapshotted_sale_items():
    schema = TABLES.read_text(encoding="utf-8").lower()
    assert "create table public.sale_items" in schema
    assert "product_code  text not null" in schema
    assert "product_name  text not null" in schema
    assert "quantity      integer not null check (quantity > 0)" in schema
    assert "unit_price    numeric(10,2) not null" in schema
    assert "generated always as (quantity * unit_price) stored" in schema
    assert "using (public.fn_is_member(company_id))" in (
        ROOT / "database/code/policies/01_security.sql"
    ).read_text(encoding="utf-8").lower()


def test_atomic_sale_rpc_locks_checks_and_completes_sale_once():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    rpc = sql.split("create or replace function public.fn_register_sale", 1)[1]
    assert "for update" in rpc
    assert "order by entry.value->>'product_code'" in rpc
    assert "v_product.stock < v_item.quantity" in rpc
    assert "insert into public.sales" in rpc
    assert "insert into public.sale_items" in rpc
    assert "public.fn_current_user_id()" in rpc
    assert "returns jsonb" in rpc
    assert "'items'" in rpc
    assert "update public.sales set status = 'concluida'" in rpc
    assert "insert into public.stock_movements" not in rpc

    trigger = COMPLETION.read_text(encoding="utf-8").lower()
    assert "insert into public.stock_movements" in trigger
    assert "'saida_venda - venda '" in trigger
    assert "public.fn_confirmed_balance" in trigger

    source = PROCEDURES.read_text(encoding="utf-8").lower()
    assert "create or replace function public.fn_create_complete_sale" in source
    assert "create or replace function public.fn_register_sale" in source


def test_client_interface_does_not_supply_item_price_to_rpc():
    source = Path(SupabaseSaleRepository.__module__.replace(".", "/") + ".py")
    source_path = ROOT / "src" / source
    text = source_path.read_text(encoding="utf-8")
    request = text.split("def register_multiple(", 1)[1].split("}).execute()", 1)[0]
    assert '"p_items": payload' in request
    assert '"product_code": item.product_code' in request
    assert '"fn_register_sale"' in text
    assert '"p_payment_method": payment_method' in request
    assert '"p_discount": str(discount)' in request
    assert '"p_unit_price"' not in request


def test_supabase_repository_returns_rpc_snapshot_without_followup_reads():
    class Client:
        def rpc(self, name, args):
            self.name = name
            self.args = args
            return SimpleNamespace(execute=lambda: SimpleNamespace(data={
                "id": "sale-id",
                "cliente": "Ana",
                "total": 29.98,
                "created_on": "2026-10-12T12:00:00Z",
                "items": [
                    {"product_code": "P-1", "product_name": "Produto 1", "quantity": 1},
                    {"product_code": "P-2", "product_name": "Produto 2", "quantity": 2},
                ],
            }))

    client = Client()
    repo = SupabaseSaleRepository(client, "company-id")
    sale = repo.register_multiple(
        SimpleNamespace(client_id="client-id", name="Ana"),
        (SaleItemInput("P-1", 1), SaleItemInput("P-2", 2)),
        Decimal("29.98"),
    )

    assert client.name == "fn_register_sale"
    assert client.args["p_items"] == [
        {"product_code": "P-1", "quantity": 1},
        {"product_code": "P-2", "quantity": 2},
    ]
    assert sale["id"] == "sale-id"
    assert sale["produto_codigo"] == ""
    assert sale["produto"] == "2 itens"
    assert sale["valor"] == "R$ 29,98"


def corpo_da_funcao(caminho, cabeca):
    """Texto da função, do CREATE até o `$$;` que a fecha."""
    texto = caminho.read_text(encoding="utf-8")
    inicio = texto.index(cabeca)
    return texto[inicio:texto.index("\n$$;", inicio) + len("\n$$;")]


REGISTER_SALE = (
    "CREATE OR REPLACE FUNCTION public.fn_register_sale(\n"
    "    p_company_id uuid,\n    p_client_id uuid,\n    p_items jsonb"
)
SALE_COMPLETION = "CREATE OR REPLACE FUNCTION public.fn_process_sale_completion()"


def test_a_migration_entrega_a_mesma_funcao_que_a_fonte_declarativa():
    """`database/code` é a fonte, mas quem roda em produção é a migration.

    As duas chegaram a ser implementações diferentes da mesma função: a
    declarativa cacheia os produtos travados em arrays, a da migration
    reconsultava produto a produto sem `FOR UPDATE` e sem `IF NOT FOUND` --
    bastava a releitura falhar para a gravação morrer em
    `sale_items.product_name NOT NULL` em vez da recusa pretendida.

    Comparar os dois arquivos é o que impede a próxima correção de ser
    aplicada só de um lado. Os testes vizinhos verificam cada arquivo
    isoladamente e por isso não viam a divergência.
    """
    for cabeca in (REGISTER_SALE, SALE_COMPLETION):
        assert corpo_da_funcao(MIGRATION, cabeca) == corpo_da_funcao(
            PROCEDURES if cabeca is REGISTER_SALE else COMPLETION, cabeca
        ), f"a migration divergiu da fonte declarativa em {cabeca.splitlines()[0]}"


def test_o_desconto_nao_pode_ter_mais_de_duas_casas():
    """numeric(10,2) arredonda `discount` e `total` por caminhos diferentes.

    Com 10.005 sobre subtotal 100.00 o banco gravava discount=10.01 e
    total=90.00: a linha deixava de fechar por R$ 0,01, que é exatamente a
    reconciliação que a coluna `discount` existe para permitir auditar.
    `fn_create_complete_sale` já exigia isso; `fn_register_sale` não.
    """
    for caminho in (PROCEDURES, MIGRATION):
        corpo = corpo_da_funcao(caminho, REGISTER_SALE)
        assert "p_discount <> round(p_discount, 2)" in corpo, caminho
        assert "(entry.value->>'quantity')::numeric > 1000000" in corpo, caminho
