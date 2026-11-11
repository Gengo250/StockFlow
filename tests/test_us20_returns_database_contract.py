"""Contratos SQL da US20 para o schema declarativo e suas migrations."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "database" / "code"
MIGRATIONS = ROOT / "database" / "supabase" / "migrations"
US15_COMPENSATION = "20261104130000_us15_compensating_cancellation.sql"
US15_CONFIRMED_ONLY = "20261105120000_us15_confirmed_sales_only.sql"


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
        Path("tables") / "06_clients_sales.sql",
        Path("tables") / "10_returns.sql",
        Path("tables") / "11_return_items.sql",
        Path("procedures") / "07_clients_sales.sql",
        Path("procedures") / "08_return_partial.sql",
        Path("triggers") / "06_sale_completion.sql",
        Path("policies") / "01_security.sql",
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


def test_current_reversal_product_locks_match_respective_migrations():
    source_path = CODE / "procedures" / "07_clients_sales.sql"
    mirror_path = ROOT / "database" / "supabase" / "schemas" / "procedures" / "07_clients_sales.sql"
    source = source_path.read_text(encoding="utf-8")
    mirror = mirror_path.read_text(encoding="utf-8")

    assert source_path.read_bytes() == mirror_path.read_bytes()
    references = {
        "fn_cancel_sale": US15_CONFIRMED_ONLY,
        "fn_return_sale": "20261031125500_us17_us20_product_lock_order.sql",
    }
    for function, filename in references.items():
        migration = (MIGRATIONS / filename).read_text(encoding="utf-8")
        definition = _function_definition(source, function)
        assert definition == _function_definition(mirror, function)
        assert definition == _function_definition(migration, function)
        assert "ORDER BY p.barcode" in definition
        assert "FOR UPDATE" in definition
        assert re.search(r"ORDER BY p\.barcode(?:, i\.id)?\s+FOR UPDATE", definition)
    assert "ORDER BY p.barcode, i.id" in _function_definition(source, "fn_return_sale")


def test_us15_incremental_migration_preserves_signature_and_execution_grants():
    migration = (
        MIGRATIONS / "20261104120000_us15_cancel_pending_validation.sql"
    ).read_text(encoding="utf-8")
    definition = _function_definition(migration, "fn_cancel_sale")
    assert "p_sale_id uuid" in definition
    assert "p_reason  text" in definition
    assert ") RETURNS jsonb" in definition
    assert "SET search_path = pg_catalog, pg_temp" in definition
    assert "jsonb_build_object('sale_id', p_sale_id, 'kind', 'CANCELAMENTO'" in definition
    assert "'reason', v_reason, 'status', 'CANCELADA'" in definition
    assert "BEGIN;" in migration
    assert migration.rstrip().endswith("COMMIT;")
    assert (
        "REVOKE ALL ON FUNCTION public.fn_cancel_sale(uuid, text)\n"
        "    FROM PUBLIC, anon, authenticated, app_backend;"
    ) in migration
    assert (
        "GRANT EXECUTE ON FUNCTION public.fn_cancel_sale(uuid, text)\n"
        "    TO app_backend, authenticated;"
    ) in migration


def test_us15_compensating_migration_matches_completion_trigger():
    source = (CODE / "triggers" / "06_sale_completion.sql").read_text(encoding="utf-8")
    migration = (MIGRATIONS / US15_COMPENSATION).read_text(encoding="utf-8")
    assert _function_definition(source, "fn_process_sale_completion") == _function_definition(
        migration, "fn_process_sale_completion"
    )
    assert "NEW.company_id, v_item.product_id, NEW.id, v_item.id, 'SAIDA'" in source


def test_us15_compensation_constraints_match_declarative_sources():
    table = (CODE / "tables" / "06_clients_sales.sql").read_text(encoding="utf-8")
    returns = (CODE / "tables" / "11_return_items.sql").read_text(encoding="utf-8")
    migration = (MIGRATIONS / US15_COMPENSATION).read_text(encoding="utf-8")
    for text in (table, migration):
        normalized = re.sub(r"\s+", " ", text)
        for contract in (
            "uq_sale_reversals_company_sale_id UNIQUE (company_id, sale_id, id)",
            "ADD COLUMN cancellation_id uuid",
            "FOREIGN KEY (company_id, sale_id, cancellation_id) "
            "REFERENCES public.sale_reversals (company_id, sale_id, id) ON DELETE RESTRICT",
            "FOREIGN KEY (company_id, sale_id, sale_item_id) "
            "REFERENCES public.sale_items (company_id, sale_id, id) ON DELETE RESTRICT",
            "cancellation_id IS NULL OR ( sale_id IS NOT NULL AND sale_item_id IS NOT NULL "
            "AND kind = 'ENTRADA' AND status = 'CONFIRMADA' "
            "AND created_by IS NOT NULL AND confirmed_on IS NOT NULL "
            "AND adjustment_reason IS NULL AND counted_balance IS NULL )",
            "CREATE UNIQUE INDEX uq_stock_movements_cancellation_item "
            "ON public.stock_movements (cancellation_id, sale_item_id) "
            "WHERE cancellation_id IS NOT NULL",
        ):
            assert contract in normalized
    for text in (returns, migration):
        assert re.search(
            r"return_id IS NULL OR \(\s+sale_id IS NOT NULL AND sale_item_id IS NOT NULL\s+"
            r"AND cancellation_id IS NULL", text,
        )


def test_us15_compensating_migration_preserves_rpc_and_limits_execution():
    migration = (MIGRATIONS / US15_COMPENSATION).read_text(encoding="utf-8")
    definition = _function_definition(migration, "fn_cancel_sale")
    assert "p_sale_id uuid" in definition
    assert "p_reason  text" in definition
    assert ") RETURNS jsonb" in definition
    assert "SET search_path = pg_catalog, pg_temp" in definition
    assert "jsonb_build_object('sale_id', p_sale_id, 'kind', 'CANCELAMENTO'" in definition
    assert "'reason', v_reason, 'status', 'CANCELADA'" in definition
    assert "BEGIN;" in migration
    assert migration.rstrip().endswith("COMMIT;")
    signatures = (
        "public.fn_cancel_sale(uuid, text)",
        "public.fn_return_partial_sale(uuid, jsonb, text, uuid)",
        "public.fn_get_returnable_items(uuid)",
    )
    revoke = re.search(
        r"REVOKE ALL ON FUNCTION (public\.fn_cancel_sale\(.*?);", migration, re.S,
    )
    grant = re.search(r"GRANT EXECUTE ON FUNCTION (.*?);", migration, re.S)
    assert revoke and grant
    for signature in signatures:
        assert signature in revoke.group(1)
        assert signature in grant.group(1)
    assert "FROM PUBLIC, anon, authenticated, app_backend" in revoke.group(1)
    assert re.search(r"TO app_backend, authenticated\s*$", grant.group(1))
    assert "fn_process_sale_completion" not in grant.group(1)
    allowlist = (CODE / "policies" / "01_security.sql").read_text(encoding="utf-8")
    for name in ("fn_cancel_sale", "fn_return_partial_sale", "fn_get_returnable_items"):
        assert f"'{name}'" in allowlist


def test_us15_compensating_migration_does_not_backfill_history():
    migration = (MIGRATIONS / US15_COMPENSATION).read_text(encoding="utf-8")
    prelude = migration[:migration.index("CREATE OR REPLACE FUNCTION")]
    prelude = re.sub(r"--[^\n]*", "", prelude)
    assert not re.search(
        r"\b(?:UPDATE\s+public\.|INSERT\s+INTO\s+public\.|DELETE\s+FROM\s+public\.)",
        prelude, re.I,
    )
    assert "CREATE TYPE" not in migration


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


def test_us15_confirmed_only_correction_keeps_data_and_rpc_contract():
    migration = (MIGRATIONS / US15_CONFIRMED_ONLY).read_text(encoding="utf-8")
    definition = _function_definition(migration, "fn_cancel_sale")
    assert definition == _function_definition((CODE / "procedures/07_clients_sales.sql").read_text(encoding="utf-8"), "fn_cancel_sale")
    assert "v_status IS DISTINCT FROM 'CONCLUIDA'" in definition
    assert "BEGIN;" in migration and migration.rstrip().endswith("COMMIT;")
    assert "FROM PUBLIC, anon, authenticated, app_backend" in migration
    assert "TO app_backend, authenticated" in migration
    assert "ALTER TABLE" not in migration and "CREATE TYPE" not in migration
