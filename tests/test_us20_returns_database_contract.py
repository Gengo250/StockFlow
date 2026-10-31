"""Contratos SQL da US20 para o schema declarativo e suas migrations."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "database" / "code"
MIGRATIONS = ROOT / "database" / "supabase" / "migrations"


def test_return_rls_matches_admin_only_rpc_authorization():
    policies = (CODE / "policies" / "02_returns_security.sql").read_text(encoding="utf-8")
    for policy in ("returns_select", "return_items_select"):
        start = policies.index(f"CREATE POLICY {policy}")
        body = policies[start:policies.index(";", start)]
        assert "fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[])" in body
        assert "fn_is_member" not in body

    migration = (MIGRATIONS / "20261030102000_us20_return_guardrails.sql").read_text(
        encoding="utf-8"
    )
    assert migration.count("fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[])") == 2


def test_return_reason_rejects_all_whitespace_in_schema_and_migration():
    table = (CODE / "tables" / "10_returns.sql").read_text(encoding="utf-8")
    migration = (MIGRATIONS / "20261030102000_us20_return_guardrails.sql").read_text(
        encoding="utf-8"
    )

    assert "CHECK (reason ~ '[^[:space:]]')" in table
    assert "DROP CONSTRAINT IF EXISTS returns_reason_check" in migration
    assert "ADD CONSTRAINT ck_returns_reason CHECK (reason ~ '[^[:space:]]')" in migration


def test_us20_schema_mirrors_remain_in_sync():
    for relative in (
        Path("tables") / "10_returns.sql",
        Path("procedures") / "08_return_partial.sql",
        Path("policies") / "02_returns_security.sql",
    ):
        assert (CODE / relative).read_bytes() == (
            ROOT / "database" / "supabase" / "schemas" / relative
        ).read_bytes()


def _function_definition(sql: str, name: str) -> str:
    start = sql.index(f"CREATE OR REPLACE FUNCTION public.{name}(")
    end = sql.index("\n$$;", start) + len("\n$$;")
    return sql[start:end]


def test_final_us20_migration_matches_declarative_return_rpc():
    source = (CODE / "procedures" / "08_return_partial.sql").read_text(encoding="utf-8")
    migration = (
        MIGRATIONS / "20261030130000_us20_discount_and_reversal_compat.sql"
    ).read_text(encoding="utf-8")
    assert _function_definition(source, "fn_return_partial_sale") == _function_definition(
        migration, "fn_return_partial_sale"
    )


def test_legacy_us17_product_locks_match_incremental_migration():
    source_path = CODE / "procedures" / "07_clients_sales.sql"
    mirror_path = ROOT / "database" / "supabase" / "schemas" / "procedures" / "07_clients_sales.sql"
    migration_path = MIGRATIONS / "20261031125500_us17_us20_product_lock_order.sql"
    source = source_path.read_text(encoding="utf-8")
    mirror = mirror_path.read_text(encoding="utf-8")
    migration = migration_path.read_text(encoding="utf-8")

    assert source_path.read_bytes() == mirror_path.read_bytes()
    for function in ("fn_cancel_sale", "fn_return_sale"):
        definition = _function_definition(source, function)
        assert definition == _function_definition(mirror, function)
        assert definition == _function_definition(migration, function)
        assert "ORDER BY p.barcode" in definition
        assert "FOR UPDATE" in definition
    assert "ORDER BY p.barcode, i.id" in _function_definition(source, "fn_return_sale")


def test_us20_and_us22_lock_products_by_barcode_in_ascending_order():
    return_sources = [
        (CODE / "procedures" / "08_return_partial.sql").read_text(encoding="utf-8"),
        *(
            (MIGRATIONS / name).read_text(encoding="utf-8")
            for name in (
                "20261030101000_us20_return_rpcs.sql",
                "20261030120000_us20_return_idempotency.sql",
                "20261030130000_us20_discount_and_reversal_compat.sql",
            )
        ),
    ]
    assert all("ORDER BY p.barcode" in source and "FOR UPDATE" in source for source in return_sources)
    assert all("ORDER BY p.id FOR UPDATE" not in source for source in return_sources)

    sale_sources = [
        (CODE / "procedures" / "13_sale_discounts.sql").read_text(encoding="utf-8"),
        (ROOT / "database" / "supabase" / "schemas" / "procedures" / "13_sale_discounts.sql")
        .read_text(encoding="utf-8"),
        (MIGRATIONS / "20261029130000_us22_sales_discounts.sql").read_text(encoding="utf-8"),
    ]
    for source in sale_sources:
        assert "ORDER BY entry.value->>'product_code'" in source
        assert "barcode = v_item.product_code" in source
        assert "FOR UPDATE" in source
