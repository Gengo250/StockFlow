from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.infrastructure.repositories.supabase_sale_repository import (
    SupabaseSaleRepository,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "database/supabase/migrations/20261006120000_atomic_multi_item_sales.sql"
)


def test_migration_adds_snapshotted_sale_items():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table public.sale_items" in sql
    assert "product_code text not null" in sql
    assert "product_name text not null" in sql
    assert "line_number  integer not null check (line_number > 0)" in sql
    assert "quantity     integer not null check (quantity > 0)" in sql
    assert "unit_price   numeric(10,2) not null" in sql
    assert "subtotal     numeric(10,2) not null" in sql
    assert "using (public.fn_is_member(company_id))" in sql


def test_atomic_sale_rpc_locks_checks_and_writes_items_and_stock_exits():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    rpc = sql.split("create or replace function public.fn_register_sale", 1)[1]
    assert "for update" in rpc
    assert "order by entry.value->>'product_code'" in rpc
    assert "v_product.stock < v_item.quantity" in rpc
    assert "insert into public.sales" in rpc
    assert "insert into public.sale_items" in rpc
    assert "insert into public.stock_movements" in rpc
    assert "'confirmada'" in rpc
    assert "saida_venda" in rpc
    assert "public.fn_current_user_id()" in rpc
    assert "returns jsonb" in rpc
    assert "'items'" in rpc


def test_client_interface_does_not_supply_price_or_total_to_rpc():
    source = Path(SupabaseSaleRepository.__module__.replace(".", "/") + ".py")
    source_path = ROOT / "src" / source
    text = source_path.read_text(encoding="utf-8")
    request = text.split('"fn_register_sale"', 1)[1].split("}).execute()", 1)[0]
    assert '"p_items": payload' in request
    assert '"p_total"' not in request
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
                    {"product_code": "P-1", "product_name": "Produto 1"},
                    {"product_code": "P-2", "product_name": "Produto 2"},
                ],
            }))

        def table(self, _name):
            raise AssertionError("A gravação deve usar só o retorno atômico da RPC.")

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
    assert sale["produto_codigo"] == "P-1, P-2"
    assert sale["valor"] == "R$ 29,98"
