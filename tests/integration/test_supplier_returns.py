"""US30 executada no schema completo e na sequência real de migrations."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest


@pytest.fixture
def case(db_tx, create_company, create_product):
    supplier = db_tx.execute("SELECT fn_create_supplier(%s,'Fornecedor US30')", (create_company,)).fetchone()[0]
    products = (create_product(stock=8), create_product(stock=4))
    codes = tuple(db_tx.execute("SELECT barcode FROM products WHERE id=%s", (product,)).fetchone()[0]
                  for product in products)
    actor = db_tx.execute("SELECT fn_current_user_id()").fetchone()[0]
    return {"company": create_company, "supplier": supplier, "products": products, "codes": codes, "actor": actor}


def items(case, quantity=2):
    return [{"product_code": case["codes"][0], "quantity": quantity, "reason": "Produto avariado"}]


def register(db, case, lines=None, *, supplier=None, purchase=None, key=None):
    return db.execute("SELECT fn_register_supplier_return(%s,%s,%s,%s,%s)",
        (case["company"], supplier or case["supplier"], Jsonb(items(case) if lines is None else lines),
         purchase, key or uuid4())).fetchone()[0]


def snapshot(db, company):
    with db.transaction(force_rollback=True):
        db.execute("RESET ROLE")
        return {table: db.execute(sql.SQL(
            "SELECT to_jsonb(t) FROM public.{} t WHERE company_id=%s ORDER BY to_jsonb(t)::text"
        ).format(sql.Identifier(table)), (company,)).fetchall()
        for table in ("products", "stock_movements", "supplier_returns", "supplier_return_items", "audit_log")}


def rejected(db, case, operation, error=psycopg.Error, match=None):
    before = snapshot(db, case["company"])
    with pytest.raises(error, match=match), db.transaction():
        operation()
    assert snapshot(db, case["company"]) == before


def login_member(db, company, *, role="STOCK", active=True, member_company=None):
    actor, auth = uuid4(), uuid4()
    db.execute("RESET ROLE")
    db.execute("INSERT INTO auth.users(id,email) VALUES (%s,%s)", (auth, f"{auth}@local.invalid"))
    db.execute("INSERT INTO user_accounts(id,name,pass_hash,auth_user_id) VALUES (%s,%s,'$auth$local-disabled-credential',%s)",
               (actor, str(actor), auth))
    db.execute("INSERT INTO company_users(company_id,user_account_id,role,active) VALUES (%s,%s,%s,%s)",
               (member_company or company, actor, role, active))
    db.execute("SET LOCAL ROLE authenticated")
    db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (str(auth),))
    return actor


def purchase_for(db, case, supplier=None, receive=True):
    purchase = db.execute("SELECT fn_create_purchase(%s,%s,%s)",
        (case["company"], supplier or case["supplier"], Jsonb([{"product_code": case["codes"][0], "quantity": 3}]))).fetchone()[0]
    if receive:
        db.execute("SELECT fn_receive_purchase(%s)", (purchase,))
    return purchase


@pytest.mark.parametrize("role", ["ADMIN", "STOCK"])
def test_authorized_return_reduces_stock_and_records_links_actor_reason_date_and_audit(db_tx, case, role):
    actor = case["actor"] if role == "ADMIN" else login_member(db_tx, case["company"])
    lines = items(case) + [{"product_code": case["codes"][1], "quantity": 1, "reason": "Entrega incorreta"}]
    result = register(db_tx, case, lines)
    assert result["created_by"] == str(actor)
    assert result["created_on"]
    assert result["supplier_id"] == str(case["supplier"])
    assert result["purchase_id"] is None
    assert result["created_by_name"]
    assert db_tx.execute("SELECT fn_get_supplier_return(%s,%s)", (case["company"], result["id"])).fetchone()[0] == result
    current = snapshot(db_tx, case["company"])
    assert {row[0]["id"]: row[0]["stock"] for row in current["products"]} == {
        str(case["products"][0]): 6, str(case["products"][1]): 3}
    exits = [row[0] for row in current["stock_movements"] if row[0]["supplier_return_id"] == result["id"]]
    assert len(exits) == len(result["items"]) == 2
    for item in result["items"]:
        movement = next(row for row in exits if row["id"] == item["movement_id"])
        assert movement["kind"] == "SAIDA"
        assert movement["status"] == "CONFIRMADA"
        assert movement["supplier_id"] == str(case["supplier"])
        assert movement["supplier_return_item_id"] == item["id"]
        assert movement["quantity"] == item["quantity"]
        assert movement["created_by"] == str(actor)
        assert movement["created_on"] == movement["confirmed_on"] == result["created_on"]
        assert item["reason"] in movement["note"]
        assert movement["sale_id"] is None and movement["return_id"] is None and movement["cancellation_id"] is None
    audit, = [row[0] for row in current["audit_log"] if row[0]["entity_id"] == result["id"]]
    assert audit["action"] == "DEVOLUCAO_FORNECEDOR"
    assert audit["is_critical"] is True
    assert audit["user_id"] == str(actor)
    assert audit["old_values"] == {"stock": {case["codes"][0]: 8, case["codes"][1]: 4}}
    assert audit["new_values"]["stock"] == {case["codes"][0]: 6, case["codes"][1]: 3}
    assert audit["new_values"]["return"] == result


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True, "2", None, 1_000_001])
def test_invalid_quantities_are_rejected_without_changes(db_tx, case, quantity):
    rejected(db_tx, case, lambda: register(db_tx, case, items(case, quantity)), psycopg.errors.CheckViolation)


@pytest.mark.parametrize("reason", [None, "", " \t\n", "x" * 1001, 42])
def test_missing_or_invalid_reason_is_rejected_without_changes(db_tx, case, reason):
    lines = items(case); lines[0]["reason"] = reason
    rejected(db_tx, case, lambda: register(db_tx, case, lines), psycopg.errors.CheckViolation)


@pytest.mark.parametrize("payload", [[], {}, [None], [{"quantity": 1}]])
def test_malformed_item_lists_are_rejected(db_tx, case, payload):
    rejected(db_tx, case, lambda: register(db_tx, case, payload), psycopg.errors.CheckViolation)


def test_duplicate_product_lines_cannot_bypass_available_stock(db_tx, case):
    rejected(db_tx, case, lambda: register(db_tx, case, items(case, 5) + items(case, 4)),
             psycopg.errors.CheckViolation, "insuficiente")
    result = register(db_tx, case, items(case, 3) + items(case, 5))
    assert len(result["items"]) == 2
    assert db_tx.execute("SELECT stock FROM products WHERE id=%s", (case["products"][0],)).fetchone()[0] == 0


def test_received_origin_is_linked_without_requiring_primary_supplier(db_tx, case):
    other = db_tx.execute("SELECT fn_create_supplier(%s,'Fornecedor principal diferente')", (case["company"],)).fetchone()[0]
    db_tx.execute("RESET ROLE")
    db_tx.execute("UPDATE products SET supplier_id=%s WHERE id=%s", (other, case["products"][0]))
    db_tx.execute("SET LOCAL ROLE authenticated")
    purchase = purchase_for(db_tx, case)
    result = register(db_tx, case, purchase=purchase)
    assert result["purchase_id"] == str(purchase)
    assert db_tx.execute("SELECT purchase_id FROM stock_movements WHERE supplier_return_id=%s", (result["id"],)).fetchone()[0] == purchase
    assert db_tx.execute("SELECT status::text FROM purchases WHERE id=%s", (purchase,)).fetchone()[0] == "RECEBIDA"
    assert db_tx.execute("SELECT stock FROM products WHERE id=%s", (case["products"][0],)).fetchone()[0] == 9


def test_origin_must_be_received_and_match_supplier_and_products(db_tx, case):
    draft = purchase_for(db_tx, case, receive=False)
    rejected(db_tx, case, lambda: register(db_tx, case, purchase=draft), match="recebida")
    db_tx.execute("SELECT fn_receive_purchase(%s)", (draft,))
    other = db_tx.execute("SELECT fn_create_supplier(%s,'Outro fornecedor')", (case["company"],)).fetchone()[0]
    rejected(db_tx, case, lambda: register(db_tx, case, supplier=other, purchase=draft), match="fornecedor")
    wrong_item = [{"product_code": case["codes"][1], "quantity": 1, "reason": "Avaria"}]
    rejected(db_tx, case, lambda: register(db_tx, case, wrong_item, purchase=draft), match="compra de origem")


def test_historical_stock_can_be_returned_after_product_and_supplier_inactivation(db_tx, case):
    db_tx.execute("RESET ROLE")
    db_tx.execute("UPDATE suppliers SET active=false WHERE id=%s", (case["supplier"],))
    db_tx.execute("UPDATE products SET active=false WHERE id=%s", (case["products"][0],))
    db_tx.execute("SET LOCAL ROLE authenticated")
    register(db_tx, case)
    assert db_tx.execute("SELECT stock,active FROM products WHERE id=%s", (case["products"][0],)).fetchone() == (6, False)


@pytest.mark.parametrize("failure", ["second_movement", "audit"])
def test_any_persistence_failure_rolls_back_stock_movements_history_and_audit(db_tx, case, failure):
    db_tx.execute("RESET ROLE")
    if failure == "second_movement":
        condition = f"NEW.supplier_return_id IS NOT NULL AND NEW.product_id='{case['products'][1]}'::uuid"
        table = "stock_movements"
    else:
        condition, table = "NEW.entity='supplier_returns'", "audit_log"
    db_tx.execute(sql.SQL("""CREATE FUNCTION us30_test_fail() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF {} THEN RAISE EXCEPTION 'falha simulada US30'; END IF; RETURN NEW; END $$;
        CREATE TRIGGER us30_test_fail BEFORE INSERT ON {} FOR EACH ROW EXECUTE FUNCTION us30_test_fail();
        """).format(sql.SQL(condition), sql.Identifier(table)))
    db_tx.execute("SET LOCAL ROLE authenticated")
    lines = items(case) + [{"product_code": case["codes"][1], "quantity": 1, "reason": "Avaria"}]
    rejected(db_tx, case, lambda: register(db_tx, case, lines), match="falha simulada US30")


def test_same_request_key_is_idempotent_and_conflicting_reuse_is_rejected(db_tx, case):
    key = uuid4()
    first = register(db_tx, case, key=key)
    before = snapshot(db_tx, case["company"])
    assert register(db_tx, case, key=key) == first
    assert snapshot(db_tx, case["company"]) == before
    rejected(db_tx, case, lambda: register(db_tx, case, items(case, 1), key=key), match="outra requisição")
    login_member(db_tx, case["company"])
    rejected(db_tx, case, lambda: register(db_tx, case, key=key), match="outra requisição")


@pytest.mark.parametrize("identity", ["seller", "inactive", "other_company", "anonymous", "inactive_company"])
def test_unauthorized_identities_cannot_write_or_read_returns(db_tx, case, identity):
    result = register(db_tx, case)
    if identity == "seller":
        login_member(db_tx, case["company"], role="SELLER")
    elif identity == "inactive":
        login_member(db_tx, case["company"], active=False)
    elif identity == "other_company":
        db_tx.execute("RESET ROLE")
        other = db_tx.execute("INSERT INTO company(name) VALUES ('Outra empresa') RETURNING id").fetchone()[0]
        login_member(db_tx, case["company"], role="ADMIN", member_company=other)
    elif identity == "anonymous":
        db_tx.execute("RESET ROLE")
        db_tx.execute("SET LOCAL ROLE anon")
        db_tx.execute("SELECT set_config('request.jwt.claim.sub','',true)")
    else:
        db_tx.execute("RESET ROLE")
        db_tx.execute("UPDATE company SET active=false WHERE id=%s", (case["company"],))
        db_tx.execute("SET LOCAL ROLE authenticated")
    for operation in (lambda: register(db_tx, case),
        lambda: db_tx.execute("SELECT fn_get_supplier_return(%s,%s)", (case["company"], result["id"])),
        lambda: db_tx.execute("SELECT fn_list_supplier_returns(%s)", (case["company"],))):
        rejected(db_tx, case, operation, psycopg.errors.InsufficientPrivilege)
    if identity != "anonymous":
        assert db_tx.execute("SELECT count(*) FROM supplier_returns").fetchone()[0] == 0
        assert db_tx.execute("SELECT count(*) FROM supplier_return_items").fetchone()[0] == 0


def test_foreign_supplier_and_unknown_product_cannot_be_attached(db_tx, case):
    db_tx.execute("RESET ROLE")
    other_company = db_tx.execute("INSERT INTO company(name) VALUES ('Outra empresa') RETURNING id").fetchone()[0]
    other_supplier = db_tx.execute("INSERT INTO suppliers(company_id,name) VALUES (%s,'Outro') RETURNING id", (other_company,)).fetchone()[0]
    db_tx.execute("SET LOCAL ROLE authenticated")
    rejected(db_tx, case, lambda: register(db_tx, case, supplier=other_supplier), psycopg.errors.ForeignKeyViolation)
    rejected(db_tx, case, lambda: register(db_tx, case, [{"product_code": "inexistente", "quantity": 1, "reason": "Avaria"}]),
             psycopg.errors.ForeignKeyViolation)


def test_history_cannot_be_written_directly_and_internal_view_is_private(db_tx, case):
    result = register(db_tx, case)
    for statement in ("INSERT INTO supplier_returns DEFAULT VALUES", "INSERT INTO supplier_return_items DEFAULT VALUES",
                      "UPDATE supplier_returns SET created_on=now()", "DELETE FROM supplier_returns",
                      "UPDATE supplier_return_items SET reason='alterado'", "DELETE FROM supplier_return_items"):
        rejected(db_tx, case, lambda statement=statement: db_tx.execute(statement), psycopg.errors.InsufficientPrivilege)
    rejected(db_tx, case, lambda: db_tx.execute("SELECT fn_supplier_return_view(%s)", (result["id"],)),
             psycopg.errors.InsufficientPrivilege)


def test_even_privileged_changes_cannot_erase_history_or_cancel_an_individual_exit(db_tx, case):
    result = register(db_tx, case)
    movement_id = result["items"][0]["movement_id"]
    rejected(db_tx, case, lambda: db_tx.execute("SELECT fn_cancel_movement(%s)", (movement_id,)), match="isoladamente")
    db_tx.execute("RESET ROLE")
    for statement in ("UPDATE supplier_returns SET created_on=now()", "DELETE FROM supplier_returns",
                      "UPDATE supplier_return_items SET reason='alterado'", "DELETE FROM supplier_return_items",
                      "DELETE FROM stock_movements WHERE supplier_return_id IS NOT NULL"):
        rejected(db_tx, case, lambda statement=statement: db_tx.execute(statement), psycopg.errors.CheckViolation)


def test_listing_combines_filters_and_pages_in_deterministic_descending_order(db_tx, case):
    purchase = purchase_for(db_tx, case)
    first = register(db_tx, case, purchase=purchase)
    second = register(db_tx, case)
    rows = db_tx.execute("SELECT fn_list_supplier_returns(%s,%s,%s)", (case["company"], case["supplier"], purchase)).fetchone()[0]
    assert rows == [first]
    ordered = sorted((first, second), key=lambda row: (row["created_on"], row["id"]), reverse=True)
    for offset in (0, 1):
        assert db_tx.execute("SELECT fn_list_supplier_returns(%s,NULL,NULL,1,%s)", (case["company"], offset)).fetchone()[0] == ordered[offset:offset+1]
    rejected(db_tx, case, lambda: db_tx.execute("SELECT fn_list_supplier_returns(%s,NULL,NULL,0,0)", (case["company"],)),
             psycopg.errors.CheckViolation)


def test_unknown_fields_in_payload_are_not_persisted_or_audited(db_tx, case):
    lines = items(case)
    lines[0].update(token="test-only-secret", password="test-only-secret", created_by=str(uuid4()))
    result = register(db_tx, case, lines)
    state = snapshot(db_tx, case["company"])
    assert "test-only-secret" not in str(state)
    assert result["created_by"] == str(case["actor"])



def test_backend_database_role_uses_the_authenticated_domain_user(db_tx, case):
    db_tx.execute("RESET ROLE")
    db_tx.execute("SET LOCAL ROLE app_backend")
    db_tx.execute("SELECT set_config('request.jwt.claim.sub','',true)")
    db_tx.execute("SELECT set_config('app.user_id',%s,true)", (str(case["actor"]),))
    result = register(db_tx, case)
    assert result["created_by"] == str(case["actor"])
    assert db_tx.execute("SELECT fn_get_supplier_return(%s,%s)", (case["company"], result["id"])).fetchone()[0] == result


@pytest.mark.parametrize("mode", ["schema", "migrations"])
@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_returns_do_not_double_apply_or_exceed_available_stock(stock_database_factory, mode, same_key):
    # Dados efetivamente commitados: as duas conexões enxergam o mesmo saldo.
    with stock_database_factory(mode) as target:
        with psycopg.connect(target, autocommit=True) as setup:
            with setup.transaction():
                company = setup.execute("INSERT INTO company(name) VALUES ('Concorrência US30') RETURNING id").fetchone()[0]
                actor = login_member(setup, company, role="ADMIN")
                auth = setup.execute("SELECT current_setting('request.jwt.claim.sub')").fetchone()[0]
                supplier = setup.execute("SELECT fn_create_supplier(%s,'Fornecedor concorrente')", (company,)).fetchone()[0]
                code = uuid4().hex
                product = setup.execute("SELECT fn_create_products(%s,%s,'Produto concorrente',20,p_stock=>3)",
                                        (company, code)).fetchone()[0]
            concurrent_case = {"company": company, "supplier": supplier, "codes": (code,)}
            key = uuid4()
            barrier = Barrier(2)
            def attempt(index):
                with psycopg.connect(target, autocommit=True) as connection:
                    try:
                        with connection.transaction():
                            connection.execute("SET LOCAL ROLE authenticated")
                            connection.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (auth,))
                            connection.execute("SET LOCAL statement_timeout='20s'")
                            barrier.wait(timeout=10)
                            result = register(connection, concurrent_case, key=key if same_key else uuid4())
                            return "ok", result["id"]
                    except psycopg.Error as error:
                        return error.sqlstate, None
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(attempt, (0, 1)))
            if same_key:
                assert [result[0] for result in results] == ["ok", "ok"]
                assert results[0][1] == results[1][1]
            else:
                assert sorted(result[0] for result in results) == ["23514", "ok"]
            assert setup.execute("SELECT stock FROM products WHERE id=%s", (product,)).fetchone()[0] == 1
            assert setup.execute("SELECT count(*) FROM supplier_returns").fetchone()[0] == 1
            assert setup.execute("SELECT count(*) FROM stock_movements WHERE supplier_return_id IS NOT NULL").fetchone()[0] == 1
            assert setup.execute("SELECT count(*) FROM audit_log WHERE entity='supplier_returns'").fetchone()[0] == 1



def test_upgrade_keeps_preexisting_purchase_and_stock_history(stock_database_factory):
    root = Path(__file__).resolve().parents[2]
    migration = root / "database/supabase/migrations/20261127040500_us30_supplier_returns.sql"
    with stock_database_factory("migrations", through_migration="20261126081500_us18_sale_payments.sql") as target:
        with psycopg.connect(target, autocommit=True) as db:
            with db.transaction():
                company = db.execute("INSERT INTO company(name) VALUES ('Upgrade US30') RETURNING id").fetchone()[0]
                actor = login_member(db, company, role="ADMIN")
                supplier = db.execute("SELECT fn_create_supplier(%s,'Fornecedor anterior')", (company,)).fetchone()[0]
                code = uuid4().hex
                product = db.execute("SELECT fn_create_products(%s,%s,'Produto anterior',20,p_stock=>5)",
                                     (company, code)).fetchone()[0]
                old_case = {"company": company, "supplier": supplier, "codes": (code,)}
                purchase = purchase_for(db, old_case)
                db.execute("RESET ROLE")
                before_product = db.execute("SELECT to_jsonb(p) FROM products p WHERE id=%s", (product,)).fetchone()[0]
                before_purchase = db.execute("SELECT to_jsonb(p) FROM purchases p WHERE id=%s", (purchase,)).fetchone()[0]
                before_movements = db.execute("SELECT to_jsonb(m) FROM stock_movements m ORDER BY id").fetchall()
            db.execute(migration.read_text())
            assert db.execute("SELECT to_jsonb(p) FROM products p WHERE id=%s", (product,)).fetchone()[0] == before_product
            assert db.execute("SELECT to_jsonb(p) FROM purchases p WHERE id=%s", (purchase,)).fetchone()[0] == before_purchase
            after_movements = db.execute("SELECT to_jsonb(m) - 'supplier_return_id' - 'supplier_return_item_id' FROM stock_movements m ORDER BY id").fetchall()
            assert after_movements == before_movements
            with db.transaction():
                db.execute("SET LOCAL ROLE app_backend")
                db.execute("SELECT set_config('app.user_id',%s,true)", (str(actor),))
                result = register(db, old_case, purchase=purchase)
                assert result["purchase_id"] == str(purchase)
                assert db.execute("SELECT stock FROM products WHERE id=%s", (product,)).fetchone()[0] == 6
