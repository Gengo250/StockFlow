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
