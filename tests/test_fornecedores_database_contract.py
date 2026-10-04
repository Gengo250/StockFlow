"""Contrato estático do schema, RLS e rotinas SQL da US08."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "database" / "code"
MIGRATION = (
    ROOT / "database" / "supabase" / "migrations"
    / "20261004180000_supplier_management.sql"
)


def code_sql():
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(CODE.rglob("*.sql"))
    )


def routine(name, source=None):
    sql = source if source is not None else code_sql()
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{name}\s*\(.*?\$\$;",
        sql, re.I | re.S,
    )
    assert match, f"Função {name} não encontrada"
    return match.group()


def test_fornecedor_documento_opcional_valido_e_unico_por_empresa():
    table = (CODE / "tables" / "07_suppliers.sql").read_text(encoding="utf-8")
    assert re.search(r"\bdocument\s+text,", table)
    assert "public.fn_valid_br_document(document)" in table
    assert "uq_suppliers_company_document" in table
    index = re.search(
        r"CREATE UNIQUE INDEX uq_suppliers_company_document(.*?);",
        table, re.I | re.S,
    ).group()
    assert "(company_id, document)" in index
    assert "active" not in index.casefold()
    assert "WHERE document IS NOT NULL AND document <> ''" in index


def test_funcoes_de_escrita_validam_papel_e_nao_apagam_registros():
    for name in (
        "fn_create_supplier", "fn_update_supplier", "fn_set_supplier_active",
        "fn_set_product_supplier", "fn_register_supplier_movement",
    ):
        body = routine(name)
        assert "SECURITY DEFINER" in body
        assert "SET search_path = public" in body
        assert "fn_has_role" in body
        assert "DELETE" not in body.upper()


def test_busca_tem_nome_documento_contatos_endereco_e_status():
    body = routine("fn_list_company_suppliers")
    for expression in (
        "s.name ILIKE", "s.document", "s.phone", "s.email", "s.address",
        "s.active",
    ):
        assert expression in body
    assert "fn_has_role" in body
    assert "ARRAY['ADMIN','STOCK']::public.user_role[]" in body


def test_historico_e_produto_guardam_vinculo_na_mesma_empresa():
    tables = (CODE / "tables" / "07_suppliers.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE public.products" in tables
    assert "supplier_id uuid" in tables
    assert "fk_products_supplier_company" in tables
    assert "fk_stock_movements_supplier_company" in tables
    assert "ON DELETE RESTRICT" in tables
    assert "ALTER TABLE public.stock_movements" in tables

    purchase = routine("fn_register_supplier_movement")
    assert "p_kind <> 'ENTRADA'" in purchase
    assert "AND active" in purchase
    assert "fn_register_movement" in purchase
    assert "UPDATE public.stock_movements SET supplier_id" in purchase


def test_fornecedor_inativo_nao_pode_ser_nova_selecao_mas_preserva_historico():
    purchase = routine("fn_register_supplier_movement")
    assert "AND active" in purchase
    product = routine("fn_set_product_supplier")
    assert "p_supplier_id IS DISTINCT FROM v_current_supplier" in product
    assert "UPDATE public.products SET supplier_id" in product
    assert "ON DELETE RESTRICT" in (
        ROOT / "database" / "code" / "tables" / "07_suppliers.sql"
    ).read_text(encoding="utf-8")


def test_rls_grants_e_migration_incremental_estao_presentes():
    security = (CODE / "policies" / "01_security.sql").read_text(encoding="utf-8")
    migration = MIGRATION.read_text(encoding="utf-8")
    assert "ALTER TABLE public.suppliers       ENABLE ROW LEVEL SECURITY" in security
    assert "CREATE POLICY suppliers_select" in security
    assert "'fn_list_company_suppliers'" in security
    assert "'fn_register_supplier_movement'" in security
    assert "CREATE TABLE public.suppliers" in migration
    assert "ALTER TABLE public.products ADD COLUMN supplier_id uuid" in migration
    assert "ALTER TABLE public.stock_movements ADD COLUMN supplier_id uuid" in migration
    assert "GRANT EXECUTE ON FUNCTION" in migration
    assert (
        ROOT / "database" / "supabase" / "schemas" / "tables" / "07_suppliers.sql"
    ).read_text(encoding="utf-8") == (
        CODE / "tables" / "07_suppliers.sql"
    ).read_text(encoding="utf-8")
    assert (
        ROOT / "database" / "supabase" / "schemas" / "procedures" / "08_suppliers.sql"
    ).read_text(encoding="utf-8") == (
        CODE / "procedures" / "08_suppliers.sql"
    ).read_text(encoding="utf-8")
