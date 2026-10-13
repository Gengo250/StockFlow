"""Contrato estático do schema e das rotinas de clientes e vendas."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CODE = RAIZ / "database" / "code"
MIGRATION = RAIZ / "database" / "supabase" / "migrations" / "20261004170000_clients_sales.sql"


def sql_code():
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(CODE.rglob("*.sql"))
    )


def routine(name):
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{name}\s*\(.*?\$\$;",
        sql_code(),
        re.I | re.S,
    )
    assert match, f"{name} não encontrada em database/code"
    return match.group()


def test_document_validator_is_used_by_client_schema_and_procedures():
    table = (CODE / "tables" / "06_clients_sales.sql").read_text(encoding="utf-8")
    assert "document <> '' AND public.fn_valid_br_document(document)" in table
    assert "length(regexp_replace(phone" in table
    assert "phone ~" in table
    assert "email ~" in table
    assert "uq_clients_company_document" in table
    assert "WHERE document IS NOT NULL AND document <> ''" in table

    for name in ("fn_create_client", "fn_update_client"):
        body = routine(name)
        assert "fn_has_role" in body
        assert "fn_valid_br_document" in body or "length(v_document)" in body


def test_client_document_uniqueness_is_scoped_to_company_and_all_statuses():
    table = (CODE / "tables" / "06_clients_sales.sql").read_text(encoding="utf-8")
    index = re.search(
        r"CREATE UNIQUE INDEX uq_clients_company_document(.*?);",
        table,
        re.I | re.S,
    ).group()
    assert "(company_id, document)" in index
    assert "active" not in index.lower()


def test_sales_keep_client_reference_and_historical_snapshots():
    """O snapshot sobrevive à mudança de modelo da US10.

    Venda virou cabeçalho + itens: o nome do cliente continua no cabeçalho e
    o nome/código do produto desceram para `sale_items`. O que este teste
    cobra não é ONDE a coluna mora, é que o histórico não dependa do cadastro
    — renomear o cliente ou apagar o produto não pode reescrever o passado.
    """
    table = (CODE / "tables" / "06_clients_sales.sql").read_text(encoding="utf-8")
    sales = re.search(r"CREATE TABLE public\.sales\s*\((.*?)\n\);", table, re.S).group(1)
    assert re.search(r"client_name\s+text\s+NOT NULL", sales, re.I)
    assert re.search(
        r"FOREIGN KEY \(company_id, client_id\).*?ON DELETE RESTRICT",
        sales,
        re.I | re.S,
    )

    itens = re.search(
        r"CREATE TABLE public\.sale_items\s*\((.*?)\n\);", table, re.S
    ).group(1)
    assert re.search(r"product_name\s+text\s+NOT NULL", itens, re.I)
    assert re.search(r"product_code\s+text\s+NOT NULL", itens, re.I)
    # SET NULL, e não RESTRICT: produto pode sair do catálogo, e a venda
    # antiga continua mostrando o que foi vendido pelo snapshot acima.
    assert re.search(
        r"FOREIGN KEY \(product_id\).*?ON DELETE SET NULL", itens, re.I | re.S
    )

    for nome in ("fn_register_sale", "fn_create_complete_sale"):
        corpo = routine(nome)
        assert "fn_has_role" in corpo, nome
        assert "AND active" in corpo, nome
        assert "INSERT INTO public.sales" in corpo, nome
        assert "INSERT INTO public.sale_items" in corpo, nome


def test_complete_sale_takes_unit_price_from_the_catalog():
    """Receber o preço do chamador deixaria quem vende escolher por quanto."""
    corpo = routine("fn_create_complete_sale")
    assinatura = re.search(
        r"fn_create_complete_sale\s*\((.*?)\)\s*RETURNS", corpo, re.S | re.I
    ).group(1).lower()
    assert "price" not in assinatura, (
        "fn_create_complete_sale aceita preço por parâmetro"
    )
    assert re.search(r"SELECT\s+name,\s*barcode,\s*sell_price", corpo, re.I), (
        "o preço unitário precisa sair de products.sell_price"
    )


def test_schema_mirror_and_migration_contain_client_contract():
    schema = (
        RAIZ / "database" / "supabase" / "schemas" / "tables" / "06_clients_sales.sql"
    ).read_text(encoding="utf-8")
    migration = MIGRATION.read_text(encoding="utf-8")
    procedures = (
        RAIZ / "database" / "supabase" / "schemas" / "procedures" / "07_clients_sales.sql"
    ).read_text(encoding="utf-8")
    assert "fn_valid_br_document" in schema
    assert "fn_create_client" in procedures
    assert "fn_register_sale" in procedures
    assert "uq_clients_company_document" in migration
    assert "fn_register_sale" in migration
