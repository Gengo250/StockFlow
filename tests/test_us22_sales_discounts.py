from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "database/code/tables/06_clients_sales.sql"
PROCEDURES = ROOT / "database/code/procedures/13_sale_discounts.sql"
TRIGGER = ROOT / "database/code/triggers/08_sale_discount_guard.sql"
POLICIES = ROOT / "database/code/policies/01_security.sql"
MIGRATION = ROOT / (
    "database/supabase/migrations/20261029130000_us22_sales_discounts.sql"
)
MIGRATIONS_DIR = ROOT / "database/supabase/migrations"


def _function_body(path, name):
    source = path.read_text(encoding="utf-8")
    start = source.index(f"CREATE OR REPLACE FUNCTION public.{name}(")
    return source[start:source.index("\n$$;", start) + len("\n$$;")]


def _ultima_migration_que_define(name):
    """A migration mais recente que define `name`, por ordem de timestamp.

    Comparar o declarativo com uma migration FIXA só funciona enquanto aquela
    for a última a tocar a função — e a regra deste repositório é justamente
    corrigir por migration NOVA, nunca editando migration já aplicada. Foi o
    que aconteceu com `fn_validate_sale_discount_limit`: a US22 a criou e
    20261031140000 a redefiniu, então o declarativo passou a divergir da
    migration da US22 por estar CERTO.

    O nome do arquivo começa pelo timestamp, então a ordem alfabética é a
    ordem de aplicação.
    """
    definem = [
        caminho
        for caminho in sorted(MIGRATIONS_DIR.glob("*.sql"))
        if f"CREATE OR REPLACE FUNCTION public.{name}(" in caminho.read_text(encoding="utf-8")
    ]
    assert definem, f"nenhuma migration define {name}"
    return definem[-1]


def test_discount_schema_keeps_original_and_final_values_with_audit():
    source = TABLES.read_text(encoding="utf-8")
    assert "original_total   numeric(10,2) GENERATED ALWAYS AS (total + discount)" in source
    assert "discount_authorized_by uuid" in source
    assert "discount_applied_by uuid" in source
    assert "discount_amount numeric(10,2)" in source
    assert "final_subtotal numeric(10,2)" in source
    assert "CREATE TABLE public.sale_discount_limits" in source


def test_sale_rpc_calculates_both_scopes_and_checks_admin_approval():
    source = PROCEDURES.read_text(encoding="utf-8")
    assert "fn_register_sale_with_discounts" in source
    assert "v_item_discount_total" in source
    assert "v_sale_discount" in source
    assert "v_discount_percent > v_limit" in source
    assert "discount_authorized_by" in source
    assert "FOR UPDATE" in source
    assert "fn_set_sale_discount_limit" in source


def test_completion_guard_covers_legacy_sale_entry_points():
    source = TRIGGER.read_text(encoding="utf-8")
    assert "BEFORE UPDATE OF status ON public.sales" in source
    assert "NEW.discount * 100 / v_original_total" in source
    assert "public.fn_is_admin" in source
    assert "NEW.discount_applied_by" in source


def test_us22_migration_matches_declarative_functions_and_grants_them():
    migration = MIGRATION.read_text(encoding="utf-8")
    for name in (
        "fn_get_sale_discount_limits",
        "fn_set_sale_discount_limit",
        "fn_register_sale_with_discounts",
        "fn_validate_sale_discount_limit",
    ):
        source_path = TRIGGER if name == "fn_validate_sale_discount_limit" else PROCEDURES
        ultima = _ultima_migration_que_define(name)
        assert _function_body(ultima, name) == _function_body(source_path, name), (
            f"{name}: o declarativo precisa bater com {ultima.name}, "
            "que é a última migration a defini-la"
        )
    assert "ALTER TABLE public.sale_discount_limits ENABLE ROW LEVEL SECURITY" in migration
    assert "GRANT EXECUTE ON FUNCTION public.fn_register_sale_with_discounts" in migration


def test_admin_only_configuration_and_discount_rpc_are_in_allowlist():
    source = POLICIES.read_text(encoding="utf-8")
    for name in (
        "fn_get_sale_discount_limits",
        "fn_set_sale_discount_limit",
        "fn_register_sale_with_discounts",
    ):
        assert f"'{name}'" in source
