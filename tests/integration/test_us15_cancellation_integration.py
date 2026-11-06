"""US15: cancelamento compensatório real em PostgreSQL local descartável.

Requer autorização específica para execução: stock_database cria/remove bancos
e aplica schema/migrations. A fixture parametriza os dois caminhos. O checkout
não é objeto destes testes: a venda nasce por INSERT privilegiado e a conclusão
passa pelos triggers reais. Nenhuma concorrência é certificada por estes casos.
"""

from contextlib import contextmanager
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest


@pytest.fixture
def sale_factory(db_tx, create_company, create_product):
    product_id = create_product(stock=10)
    register = db_tx.execute(
        "SELECT public.fn_start_my_register(%s,0)", (create_company,),
    ).fetchone()[0]
    actor = db_tx.execute("SELECT public.fn_current_user_id()").fetchone()[0]

    def create(status="PENDENTE"):
        sale_id, item_id = uuid4(), uuid4()
        db_tx.execute("RESET ROLE")
        db_tx.execute(
            "INSERT INTO public.sales "
            "(id,company_id,client_name,total,status,created_by,register_log_id) "
            "VALUES (%s,%s,'Cliente US15',40,'PENDENTE',%s,%s)",
            (sale_id, create_company, actor, register["id"]),
        )
        db_tx.execute(
            "INSERT INTO public.sale_items "
            "(id,company_id,sale_id,product_id,product_name,product_code,quantity,unit_price) "
            "SELECT %s,%s,%s,id,name,barcode,2,20 FROM public.products WHERE id=%s",
            (item_id, create_company, sale_id, product_id),
        )
        if status == "CONCLUIDA":
            db_tx.execute(
                "UPDATE public.sales SET status='CONCLUIDA' WHERE id=%s", (sale_id,),
            )
        else:
            assert status == "PENDENTE"
        db_tx.execute("SET LOCAL ROLE authenticated")
        return {
            "sale_id": sale_id, "item_id": item_id, "product_id": product_id,
            "company_id": create_company, "actor": actor,
            "register_id": register["id"], "status": status,
        }

    return create


@pytest.fixture(params=("PENDENTE", "CONCLUIDA"))
def sale_case(request, sale_factory):
    return sale_factory(request.param)


@pytest.fixture
def multi_item_sale(db_tx, sale_factory, create_product):
    case = sale_factory("PENDENTE")
    second_product = create_product(stock=7)
    with privileged(db_tx):
        db_tx.execute(
            "INSERT INTO public.sale_items "
            "(id,company_id,sale_id,product_id,product_name,product_code,quantity,unit_price) "
            "SELECT %s,%s,%s,id,name,barcode,3,20 FROM public.products WHERE id=%s",
            (uuid4(), case["company_id"], case["sale_id"], second_product),
        )
        db_tx.execute(
            "UPDATE public.sales SET total=100,status='CONCLUIDA' WHERE id=%s",
            (case["sale_id"],),
        )
    return {
        **case, "status": "CONCLUIDA",
        "product_ids": [case["product_id"], second_product],
    }


@contextmanager
def privileged(db):
    """Preparação local em savepoint; restaura o papel até quando há exceção."""
    role = db.execute("SELECT current_user").fetchone()[0]
    try:
        with db.transaction():
            db.execute("RESET ROLE")
            yield
    finally:
        db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))


def state(db, case):
    """Leitura privilegiada em savepoint, sem ocultar efeitos por RLS.

    O rollback do savepoint restaura o papel do chamador. As linhas retornadas
    permitem conferir também falhas provocadas por outro usuário ou por anon.
    """
    product_ids = case.get("product_ids", [case["product_id"]])
    with db.transaction(force_rollback=True):
        db.execute("RESET ROLE")
        return {
            "sale_row": db.execute(
                "SELECT to_jsonb(s) FROM public.sales s WHERE s.id=%s",
                (case["sale_id"],),
            ).fetchone()[0],
            "sale": db.execute(
                "SELECT status::text,total,discount,created_by,register_log_id "
                "FROM public.sales WHERE id=%s", (case["sale_id"],),
            ).fetchall(),
            "items": db.execute(
                "SELECT * FROM public.sale_items WHERE sale_id=%s ORDER BY id",
                (case["sale_id"],),
            ).fetchall(),
            "product": db.execute(
                "SELECT id,stock FROM public.products WHERE id=%s", (case["product_id"],),
            ).fetchall(),
            "products": db.execute(
                "SELECT to_jsonb(p) FROM public.products p WHERE id=ANY(%s) ORDER BY id",
                (product_ids,),
            ).fetchall(),
            "product_stock": db.execute(
                "SELECT * FROM public.product_stock WHERE product_id=ANY(%s) "
                "ORDER BY product_id", (product_ids,),
            ).fetchall(),
            "movements": db.execute(
                "SELECT * FROM public.stock_movements "
                "WHERE product_id=ANY(%s) OR sale_id=%s ORDER BY id",
                (product_ids, case["sale_id"]),
            ).fetchall(),
            "reversal_rows": db.execute(
                "SELECT * FROM public.sale_reversals WHERE sale_id=%s ORDER BY id",
                (case["sale_id"],),
            ).fetchall(),
            "reversals": db.execute(
                "SELECT kind::text,reason,created_by,created_on "
                "FROM public.sale_reversals WHERE sale_id=%s ORDER BY id",
                (case["sale_id"],),
            ).fetchall(),
            "sales_log": db.execute(
                "SELECT * FROM public.sales_log WHERE sale_id=%s ORDER BY id",
                (case["sale_id"],),
            ).fetchall(),
            "returns": db.execute(
                "SELECT * FROM public.returns WHERE sale_id=%s ORDER BY id",
                (case["sale_id"],),
            ).fetchall(),
            "return_items": db.execute(
                "SELECT * FROM public.return_items WHERE sale_id=%s ORDER BY id",
                (case["sale_id"],),
            ).fetchall(),
            "register": db.execute(
                "SELECT * FROM public.register_log WHERE id=%s", (case["register_id"],),
            ).fetchall(),
        }


def cancel(db, case, reason="Venda incorreta"):
    return db.execute(
        "SELECT public.fn_cancel_sale(%s,%s)", (case["sale_id"], reason),
    ).fetchone()[0]


def assert_rejected(db, case, error, reason="Venda incorreta", match=None):
    return assert_operation_rejected(
        db, case, lambda: cancel(db, case, reason), error, match,
    )


def assert_operation_rejected(db, case, operation, error, match=None):
    before = state(db, case)
    with pytest.raises(error, match=match) as raised, db.transaction():
        operation()
    assert state(db, case) == before
    return raised.value


def assert_compensated(db, case, before):
    """Compara todas as linhas antigas e confere exatamente uma entrada por item."""
    after = state(db, case)
    assert after["sale_row"] == {**before["sale_row"], "status": "CANCELADA"}
    for key in ("items", "sales_log", "returns", "return_items", "register", "product_stock"):
        assert after[key] == before[key]
    old_movements = {row[0]: row for row in before["movements"]}
    current_movements = {row[0]: row for row in after["movements"]}
    # Inclui a saída completa: id, vínculos, autoria, instantes, nota e status.
    for movement_id, original in old_movements.items():
        assert current_movements[movement_id] == original

    items = db.execute(
        "SELECT id,product_id,quantity FROM public.sale_items WHERE sale_id=%s ORDER BY id",
        (case["sale_id"],),
    ).fetchall()
    expected = {str(item_id): (str(product_id), quantity) for item_id, product_id, quantity in items}
    cancellation_id, = db.execute(
        "SELECT id FROM public.sale_reversals WHERE sale_id=%s AND kind='CANCELAMENTO'",
        (case["sale_id"],),
    ).fetchone()
    entries = [row[0] for row in db.execute(
        "SELECT to_jsonb(sm) FROM public.stock_movements sm "
        "WHERE sale_id=%s AND cancellation_id IS NOT NULL ORDER BY sale_item_id",
        (case["sale_id"],),
    ).fetchall()]
    assert len(entries) == len(expected)
    assert {entry["sale_item_id"] for entry in entries} == set(expected)
    assert set(current_movements) - set(old_movements) == {UUID(entry["id"]) for entry in entries}
    quantities = {}
    for entry in entries:
        product_id, quantity = expected[entry["sale_item_id"]]
        assert entry["company_id"] == str(case["company_id"])
        assert entry["sale_id"] == str(case["sale_id"])
        assert entry["product_id"] == product_id
        assert entry["quantity"] == quantity
        assert entry["cancellation_id"] == str(cancellation_id)
        assert entry["kind"] == "ENTRADA"
        assert entry["status"] == "CONFIRMADA"
        assert entry["created_by"] == str(case["actor"])
        assert entry["confirmed_on"] is not None
        assert entry["created_on"] is not None
        assert entry["return_id"] is None
        assert entry["adjustment_reason"] is None
        assert entry["counted_balance"] is None
        quantities[product_id] = quantities.get(product_id, 0) + quantity
    old_products = {row[0]["id"]: row[0] for row in before["products"]}
    for (product,) in after["products"]:
        assert product["stock"] == old_products[product["id"]]["stock"] + quantities[product["id"]]
    return after


def return_items(db, case, quantity):
    return db.execute(
        "SELECT public.fn_return_partial_sale(%s,%s,%s,%s)",
        (case["sale_id"], Jsonb([{
            "sale_item_id": str(case["item_id"]), "quantity": quantity,
        }]), "Produto retornou", uuid4()),
    ).fetchone()[0]


def copy_compensation(db, case, sale_item_id=None, return_id=None):
    db.execute(
        "INSERT INTO public.stock_movements "
        "(company_id,product_id,sale_id,sale_item_id,cancellation_id,return_id,"
        "kind,quantity,status,created_by,confirmed_on) "
        "SELECT company_id,product_id,sale_id,COALESCE(%s::uuid,sale_item_id),"
        "cancellation_id,%s::uuid,kind,quantity,status,created_by,confirmed_on "
        "FROM public.stock_movements WHERE sale_id=%s AND cancellation_id IS NOT NULL",
        (sale_item_id, return_id, case["sale_id"]),
    )


def switch_user(db, company_id, role):
    user_id, auth_id = uuid4(), uuid4()
    db.execute("RESET ROLE")
    db.execute(
        "INSERT INTO auth.users(id,email) VALUES (%s,%s)",
        (auth_id, f"{user_id.hex}@local.invalid"),
    )
    db.execute(
        "INSERT INTO public.user_accounts(id,name,pass_hash,auth_user_id) "
        "VALUES (%s,%s,'$auth$local-disabled-credential',%s)",
        (user_id, user_id.hex, auth_id),
    )
    db.execute(
        "INSERT INTO public.company_users(company_id,user_account_id,role) VALUES (%s,%s,%s)",
        (company_id, user_id, role),
    )
    db.execute("SET LOCAL ROLE authenticated")
    db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (str(auth_id),))


@pytest.mark.parametrize("reason", [" \tVenda incorreta\r\n ", "x" * 300], ids=["trim", "limit"])
def test_admin_cancels_only_concluded_and_preserves_commercial_data(db_tx, sale_case, reason):
    if sale_case["status"] == "PENDENTE":
        assert_rejected(db_tx, sale_case, psycopg.errors.CheckViolation, reason, match="concluída")
        return
    before = state(db_tx, sale_case)
    result = cancel(db_tx, sale_case, reason)
    after = state(db_tx, sale_case)

    assert result == {
        "sale_id": str(sale_case["sale_id"]), "kind": "CANCELAMENTO",
        "reason": reason.strip(), "status": "CANCELADA",
    }
    assert after["sale"][0][0] == "CANCELADA"
    assert after["sale"][0][1:] == before["sale"][0][1:]
    assert after["product"][0][1] == 10
    assert after["items"] == before["items"]
    assert after["sales_log"] == before["sales_log"]
    assert after["returns"] == before["returns"]
    assert after["return_items"] == before["return_items"]
    assert after["register"] == before["register"]
    reversal, = after["reversals"]
    assert reversal[:3] == ("CANCELAMENTO", reason.strip(), sale_case["actor"])
    assert reversal[3] is not None
    assert before["product"][0][1] == 8
    assert_compensated(db_tx, sale_case, before)


@pytest.mark.parametrize("role", ["SELLER", "STOCK"])
def test_non_admin_cannot_cancel(db_tx, sale_case, role):
    switch_user(db_tx, sale_case["company_id"], role)
    assert_rejected(db_tx, sale_case, psycopg.errors.InsufficientPrivilege)


def test_admin_from_other_company_cannot_cancel(db_tx, sale_case):
    other_company = uuid4()
    db_tx.execute("RESET ROLE")
    db_tx.execute(
        "INSERT INTO public.company(id,name) VALUES (%s,'Outra empresa US15')", (other_company,),
    )
    switch_user(db_tx, other_company, "ADMIN")
    assert_rejected(db_tx, sale_case, psycopg.errors.InsufficientPrivilege)


def test_missing_identity_cannot_cancel(db_tx, sale_case):
    db_tx.execute("SELECT set_config('request.jwt.claim.sub','',true)")
    db_tx.execute("SELECT set_config('app.user_id','',true)")
    assert_rejected(db_tx, sale_case, psycopg.errors.InsufficientPrivilege)


def test_anon_cannot_execute_cancellation(db_tx, sale_case):
    db_tx.execute("SET LOCAL ROLE anon")
    assert_rejected(db_tx, sale_case, psycopg.errors.InsufficientPrivilege)


@pytest.mark.parametrize(
    "reason", [None, "", "   ", "\t", "\n", " \t\r\n ", "x" * 301],
    ids=["null", "empty", "spaces", "tab", "newline", "mixed", "too-long"],
)
def test_invalid_reason_has_no_partial_effects(db_tx, sale_case, reason):
    assert_rejected(db_tx, sale_case, psycopg.errors.CheckViolation, reason)


def test_duplicate_cancellation_has_no_partial_effects(db_tx, sale_case):
    if sale_case["status"] == "PENDENTE":
        assert_rejected(db_tx, sale_case, psycopg.errors.CheckViolation)
        return
    cancel(db_tx, sale_case)
    assert_rejected(db_tx, sale_case, psycopg.errors.CheckViolation)


@pytest.mark.parametrize("kind", ["ENTRADA", "SAIDA"])
def test_inconsistent_pending_sale_cannot_cancel(db_tx, sale_factory, kind):
    case = sale_factory("PENDENTE")
    db_tx.execute("RESET ROLE")
    db_tx.execute(
        "INSERT INTO public.stock_movements "
        "(company_id,product_id,sale_id,sale_item_id,kind,quantity,status,created_by,confirmed_on) "
        "VALUES (%s,%s,%s,%s,%s,1,'CONFIRMADA',%s,now())",
        (case["company_id"], case["product_id"], case["sale_id"], case["item_id"], kind, case["actor"]),
    )
    db_tx.execute("SET LOCAL ROLE authenticated")
    assert_rejected(
        db_tx, case, psycopg.errors.CheckViolation,
        match="concluída",
    )


def test_closed_register_rejection_rolls_back_cancellation(db_tx, sale_case):
    declared = 40 if sale_case["status"] == "CONCLUIDA" else 0
    db_tx.execute(
        "SELECT public.fn_close_register_session(%s,%s)",
        (sale_case["register_id"], declared),
    )
    assert_rejected(db_tx, sale_case, psycopg.Error,
                    match="caixa fechado" if sale_case["status"] == "CONCLUIDA" else "concluída")


@pytest.fixture
def reject_final_update(db_tx):
    # DDL exclusivamente no banco descartável, desfeito pela fixture db_tx.
    # Não basta falhar: conferir auditoria, saídas e TODAS as compensações antes.
    db_tx.execute("RESET ROLE")
    db_tx.execute("""
        CREATE FUNCTION public.us15_test_reject_cancel() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
        BEGIN
            IF NEW.status = 'CANCELADA' THEN
                IF NOT EXISTS (
                    SELECT 1 FROM public.sale_reversals r
                    WHERE r.sale_id=OLD.id AND r.kind='CANCELAMENTO'
                ) THEN
                    RAISE EXCEPTION 'Auditoria não foi registrada antes da falha'
                        USING ERRCODE='XX000';
                END IF;
                IF OLD.status = 'CONCLUIDA' AND EXISTS (
                    SELECT 1 FROM public.sale_items i WHERE i.sale_id=OLD.id AND (
                        (SELECT count(*) FROM public.stock_movements sm
                         WHERE sm.sale_id=OLD.id AND sm.sale_item_id=i.id
                           AND sm.product_id=i.product_id AND sm.quantity=i.quantity
                           AND sm.kind='SAIDA' AND sm.status='CONFIRMADA'
                           AND sm.cancellation_id IS NULL) <> 1
                        OR (SELECT count(*) FROM public.stock_movements sm
                            JOIN public.sale_reversals r ON r.id=sm.cancellation_id
                             AND r.company_id=sm.company_id AND r.sale_id=sm.sale_id
                            WHERE sm.sale_id=OLD.id AND sm.sale_item_id=i.id
                              AND sm.product_id=i.product_id AND sm.quantity=i.quantity
                              AND sm.kind='ENTRADA' AND sm.status='CONFIRMADA'
                              AND r.kind='CANCELAMENTO') <> 1
                    )
                ) THEN
                    RAISE EXCEPTION 'Saídas ou compensações incorretas antes da falha'
                        USING ERRCODE='XX000';
                END IF;
                IF OLD.status = 'PENDENTE' AND EXISTS (
                    SELECT 1 FROM public.stock_movements sm
                     WHERE sm.sale_id=OLD.id AND sm.cancellation_id IS NOT NULL
                ) THEN
                    RAISE EXCEPTION 'Pendência recebeu compensação indevida'
                        USING ERRCODE='XX000';
                END IF;
                RAISE EXCEPTION 'Falha US15 após auditoria e compensação' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER zz_us15_test_reject_cancel BEFORE UPDATE OF status ON public.sales
        FOR EACH ROW EXECUTE FUNCTION public.us15_test_reject_cancel();
    """)
    db_tx.execute("SET LOCAL ROLE authenticated")


def test_late_failure_rolls_back_audit_stock_and_sale(db_tx, sale_case, reject_final_update):
    assert_rejected(
        db_tx, sale_case, psycopg.errors.CheckViolation,
        match="Falha US15 após auditoria e compensação" if sale_case["status"] == "CONCLUIDA" else "concluída",
    )


def test_late_failure_rolls_back_all_products(db_tx, multi_item_sale, reject_final_update):
    assert_rejected(
        db_tx, multi_item_sale, psycopg.errors.CheckViolation,
        match="Falha US15 após auditoria e compensação",
    )


@pytest.mark.parametrize("signature", [
    "public.fn_cancel_sale(uuid,text)",
    "public.fn_return_partial_sale(uuid,jsonb,text,uuid)",
    "public.fn_get_returnable_items(uuid)",
])
def test_reversal_execution_grants(db_tx, create_company, signature):
    # create_company também garante que schema/migrations foram preparados.
    for role, allowed in (("anon", False), ("authenticated", True), ("app_backend", True)):
        assert db_tx.execute(
            "SELECT has_function_privilege(%s,%s,'EXECUTE')",
            (role, signature),
        ).fetchone()[0] is allowed


def test_multiple_items_are_compensated_without_changing_originals(db_tx, multi_item_sale):
    before = state(db_tx, multi_item_sale)
    cancel(db_tx, multi_item_sale)
    after = assert_compensated(db_tx, multi_item_sale, before)
    assert {row[0]["stock"] for row in after["products"]} == {10, 7}


def test_repeated_product_lines_receive_one_compensation_each(db_tx, sale_factory):
    case = sale_factory("PENDENTE")
    with privileged(db_tx):
        db_tx.execute(
            "INSERT INTO public.sale_items "
            "(id,company_id,sale_id,product_id,product_name,product_code,quantity,unit_price) "
            "SELECT %s,company_id,sale_id,product_id,product_name,product_code,3,20 "
            "FROM public.sale_items WHERE id=%s", (uuid4(), case["item_id"]),
        )
        db_tx.execute(
            "UPDATE public.sales SET total=100,status='CONCLUIDA' WHERE id=%s",
            (case["sale_id"],),
        )
    before = state(db_tx, case)
    assert before["product"][0][1] == 5
    cancel(db_tx, case)
    after = assert_compensated(db_tx, case, before)
    assert after["product"][0][1] == 10


@pytest.mark.parametrize("inconsistency", [
    "missing-link", "wrong-quantity", "missing-output", "cancelled-output", "missing-confirmation",
])
def test_inconsistent_concluded_sale_is_rejected_without_backfill(
    db_tx, sale_factory, inconsistency,
):
    case = sale_factory("CONCLUIDA")
    statements = {
        "missing-link": "UPDATE public.stock_movements SET sale_item_id=NULL WHERE sale_id=%s",
        "wrong-quantity": "UPDATE public.stock_movements SET quantity=1 WHERE sale_id=%s",
        "missing-output": "DELETE FROM public.stock_movements WHERE sale_id=%s",
        "cancelled-output": "UPDATE public.stock_movements SET status='CANCELADA' WHERE sale_id=%s",
        "missing-confirmation": "UPDATE public.stock_movements SET confirmed_on=NULL WHERE sale_id=%s",
    }
    # Simula histórico que antecede as proteções/vínculos atuais. Só a guarda
    # de imutabilidade é suspensa, só na preparação do banco descartável. Ela
    # deve estar habilitada novamente ANTES de chamar a RPC que estamos testando.
    with privileged(db_tx):
        db_tx.execute("ALTER TABLE public.stock_movements DISABLE TRIGGER trg_protect_confirmed_movement")
        try:
            db_tx.execute(statements[inconsistency], (case["sale_id"],))
        finally:
            db_tx.execute("ALTER TABLE public.stock_movements ENABLE TRIGGER trg_protect_confirmed_movement")
    assert db_tx.execute(
        "SELECT tgenabled FROM pg_trigger WHERE tgrelid='public.stock_movements'::regclass "
        "AND tgname='trg_protect_confirmed_movement'",
    ).fetchone()[0] == "O"
    assert_rejected(db_tx, case, psycopg.errors.CheckViolation, match="Inconsistência")


def test_duplicate_output_is_rejected_without_compensation(db_tx, sale_factory):
    case = sale_factory("CONCLUIDA")
    with privileged(db_tx):
        db_tx.execute(
            "INSERT INTO public.stock_movements "
            "(company_id,product_id,sale_id,sale_item_id,kind,quantity,status,created_by,confirmed_on) "
            "SELECT company_id,product_id,sale_id,sale_item_id,kind,quantity,status,created_by,confirmed_on "
            "FROM public.stock_movements WHERE sale_id=%s", (case["sale_id"],),
        )
    assert_rejected(db_tx, case, psycopg.errors.CheckViolation, match="Inconsistência")


def test_missing_product_is_rejected_without_compensation(db_tx, sale_factory):
    case = sale_factory("CONCLUIDA")
    with privileged(db_tx):
        db_tx.execute(
            "UPDATE public.sale_items SET product_id=NULL WHERE id=%s", (case["item_id"],),
        )
    assert_rejected(db_tx, case, psycopg.errors.CheckViolation, match="Inconsistência")


def test_inactive_product_can_be_restituted_without_reactivation(db_tx, sale_factory):
    case = sale_factory("CONCLUIDA")
    db_tx.execute("SELECT public.fn_set_product_active(%s,false)", (case["product_id"],))
    before = state(db_tx, case)
    cancel(db_tx, case)
    after = assert_compensated(db_tx, case, before)
    assert after["products"][0][0]["active"] is False


@pytest.mark.parametrize("quantity", [1, 2], ids=["partial", "total"])
def test_completed_return_blocks_cancellation(db_tx, sale_factory, quantity):
    case = sale_factory("CONCLUIDA")
    result = return_items(db_tx, case, quantity)
    assert result["is_total_return"] is (quantity == 2)
    before = state(db_tx, case)
    assert len(before["returns"]) == len(before["return_items"]) == 1
    assert before["product"][0][1] == 8 + quantity
    assert_rejected(db_tx, case, psycopg.errors.CheckViolation, match="devolução registrada")


def test_cancellation_blocks_new_return_and_rolls_back_request(db_tx, sale_factory):
    case = sale_factory("CONCLUIDA")
    cancel(db_tx, case)
    assert_operation_rejected(
        db_tx, case, lambda: return_items(db_tx, case, 1),
        psycopg.errors.CheckViolation, match="Somente venda concluída",
    )


def assert_stock_maximum_rejected(db_tx, case):
    # No caso múltiplo, a última entrada na ordem dos locks excederá o máximo.
    # A primeira já teria restituído outro produto: seu efeito também deve voltar.
    product_id, stock, quantity = db_tx.execute(
        "SELECT p.id,p.stock,i.quantity FROM public.sale_items i "
        "JOIN public.products p ON p.id=i.product_id "
        "WHERE i.sale_id=%s ORDER BY p.barcode DESC,i.id DESC LIMIT 1",
        (case["sale_id"],),
    ).fetchone()
    db_tx.execute("SELECT public.fn_set_min_stock(%s,0)", (product_id,))
    maximum = stock + quantity - 1
    db_tx.execute("SELECT public.fn_set_max_stock(%s,%s)", (product_id, maximum))
    assert_rejected(db_tx, case, psycopg.errors.CheckViolation, match="estoque máximo")


def test_stock_maximum_rejection_is_atomic(db_tx, sale_factory):
    assert_stock_maximum_rejected(db_tx, sale_factory("CONCLUIDA"))


def test_stock_maximum_rejection_rolls_back_all_products(db_tx, multi_item_sale):
    assert_stock_maximum_rejected(db_tx, multi_item_sale)


@pytest.mark.parametrize("role", ["anon", "authenticated", "app_backend"])
@pytest.mark.parametrize("table", [
    "sales", "sale_items", "sale_reversals", "stock_movements", "returns", "return_items",
])
def test_application_roles_have_no_direct_write_grants(db_tx, create_company, role, table):
    for privilege in ("INSERT", "UPDATE", "DELETE"):
        assert db_tx.execute(
            "SELECT has_table_privilege(%s,%s,%s)",
            (role, f"public.{table}", privilege),
        ).fetchone()[0] is False


@pytest.mark.parametrize("role", ["anon", "authenticated", "app_backend"])
@pytest.mark.parametrize("target", ["sale", "item", "audit", "original", "compensation"])
@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
def test_direct_writes_are_denied_and_preserve_commercial_history(
    db_tx, sale_factory, role, target, operation,
):
    case = sale_factory("CONCLUIDA")
    cancel(db_tx, case)
    # Todas as linhas alvo existem: UPDATE/DELETE não podem passar apenas por
    # não encontrar registros. A leitura de conferência ignora RLS via state().
    tables = {
        "sale": ("sales", case["sale_id"], "total"),
        "item": ("sale_items", case["item_id"], "quantity"),
        "audit": ("sale_reversals", db_tx.execute(
            "SELECT id FROM public.sale_reversals WHERE sale_id=%s", (case["sale_id"],),
        ).fetchone()[0], "reason"),
    }
    for name, kind in (("original", "SAIDA"), ("compensation", "ENTRADA")):
        movement_id = db_tx.execute(
            "SELECT id FROM public.stock_movements WHERE sale_id=%s AND kind=%s",
            (case["sale_id"], kind),
        ).fetchone()[0]
        tables[name] = ("stock_movements", movement_id, "quantity")
    table, row_id, field = tables[target]
    if operation == "insert":
        # Colunas explícitas: não tentar inserir subtotal/original_total gerados.
        columns = {
            "sales": ("company_id", "client_name", "total", "status", "created_by", "register_log_id"),
            "sale_items": ("company_id", "sale_id", "product_id", "product_name", "product_code", "quantity", "unit_price"),
            "sale_reversals": ("company_id", "sale_id", "kind", "reason", "created_by"),
            "stock_movements": ("company_id", "product_id", "sale_id", "sale_item_id", "cancellation_id",
                                "return_id", "kind", "quantity", "status", "created_by", "confirmed_on"),
        }[table]
        values = db_tx.execute(sql.SQL("SELECT {} FROM public.{} WHERE id=%s").format(
            sql.SQL(",").join(map(sql.Identifier, columns)), sql.Identifier(table),
        ), (row_id,)).fetchone()
        query = sql.SQL("INSERT INTO public.{} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, ("id", *columns))),
            sql.SQL(",").join(sql.Placeholder() for _ in range(len(columns) + 1)),
        )
        params = (uuid4(), *values)
    elif operation == "update":
        query = sql.SQL("UPDATE public.{} SET {}=%s WHERE id=%s").format(
            sql.Identifier(table), sql.Identifier(field),
        )
        params = ("Auditoria adulterada" if target == "audit" else 99, row_id)
    else:
        query = sql.SQL("DELETE FROM public.{} WHERE id=%s").format(sql.Identifier(table))
        params = (row_id,)
    before = state(db_tx, case)
    with db_tx.transaction(force_rollback=True):
        # Falhar aqui é pré-requisito de ambiente ausente, NÃO prova de que o
        # DML foi recusado. Não adicionar grants para o executor silenciosamente.
        db_tx.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
        assert db_tx.execute("SELECT current_user").fetchone()[0] == role
        if role == "app_backend":
            db_tx.execute("SELECT set_config('request.jwt.claim.sub','',true)")
            db_tx.execute("SELECT set_config('app.user_id',%s,true)", (str(case["actor"]),))
            assert db_tx.execute("SELECT public.fn_current_user_id()").fetchone()[0] == case["actor"]
        elif role == "anon":
            db_tx.execute("SELECT set_config('request.jwt.claim.sub','',true)")
            db_tx.execute("SELECT set_config('app.user_id','',true)")
        else:
            assert db_tx.execute("SELECT public.fn_current_user_id()").fetchone()[0] == case["actor"]
        with pytest.raises(psycopg.errors.InsufficientPrivilege), db_tx.transaction():
            db_tx.execute(query, params)
        assert state(db_tx, case) == before
    assert state(db_tx, case) == before


def test_duplicate_compensation_is_rejected_by_unique_index(db_tx, sale_factory):
    case = sale_factory("CONCLUIDA")
    cancel(db_tx, case)
    with privileged(db_tx):
        error = assert_operation_rejected(
            db_tx, case, lambda: copy_compensation(db_tx, case), psycopg.errors.UniqueViolation,
        )
    assert error.diag.constraint_name == "uq_stock_movements_cancellation_item"


def test_compensation_cannot_reference_an_item_from_another_sale(db_tx, sale_factory):
    case = sale_factory("CONCLUIDA")
    other = sale_factory("PENDENTE")
    cancel(db_tx, case)
    with privileged(db_tx):
        error = assert_operation_rejected(
            db_tx, case, lambda: copy_compensation(db_tx, case, sale_item_id=other["item_id"]),
            psycopg.errors.ForeignKeyViolation,
        )
    assert error.diag.constraint_name == "fk_stock_movements_sale_item_scope"


def test_compensation_cannot_also_be_a_return(db_tx, sale_factory):
    case = sale_factory("CONCLUIDA")
    cancel(db_tx, case)
    with privileged(db_tx):
        error = assert_operation_rejected(
            db_tx, case, lambda: copy_compensation(db_tx, case, return_id=uuid4()),
            psycopg.errors.CheckViolation,
        )
    assert error.diag.constraint_name == "ck_stock_movements_return"


def test_compensation_cannot_be_cancelled_in_isolation(db_tx, sale_factory):
    case = sale_factory("CONCLUIDA")
    cancel(db_tx, case)
    with privileged(db_tx):
        error = assert_operation_rejected(
            db_tx, case, lambda: db_tx.execute(
                "UPDATE public.stock_movements SET status='CANCELADA' "
                "WHERE sale_id=%s AND cancellation_id IS NOT NULL", (case["sale_id"],),
            ), psycopg.errors.CheckViolation,
        )
    assert error.diag.constraint_name == "ck_stock_movements_cancellation"


@pytest.mark.parametrize("kind", ["SAIDA", "ENTRADA"])
@pytest.mark.parametrize("operation", ["edit", "delete"])
def test_original_and_compensation_are_protected_from_edit_and_delete(
    db_tx, sale_factory, kind, operation,
):
    case = sale_factory("CONCLUIDA")
    cancel(db_tx, case)
    statement = (
        "UPDATE public.stock_movements SET quantity=quantity+1 WHERE sale_id=%s AND kind=%s"
        if operation == "edit" else
        "DELETE FROM public.stock_movements WHERE sale_id=%s AND kind=%s"
    )
    with privileged(db_tx):
        assert_operation_rejected(
            db_tx, case, lambda: db_tx.execute(statement, (case["sale_id"], kind)),
            psycopg.errors.CheckViolation, match="Movimentação confirmada não pode",
        )
