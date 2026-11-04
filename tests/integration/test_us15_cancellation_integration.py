"""US15, tarefa 1: RPC real em PostgreSQL local descartável.

Requer autorização específica para execução: stock_database cria/remove bancos
e aplica schema/migrations. A fixture parametriza os dois caminhos. O checkout
não é objeto destes testes: a venda nasce por INSERT privilegiado e a conclusão
passa pelos triggers reais. Nenhuma concorrência é certificada por estes casos.
"""

from uuid import uuid4

import psycopg
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


def state(db, case):
    """Leitura privilegiada em savepoint, sem ocultar efeitos por RLS.

    O rollback do savepoint restaura o papel do chamador. As linhas retornadas
    permitem conferir também falhas provocadas por outro usuário ou por anon.
    """
    with db.transaction(force_rollback=True):
        db.execute("RESET ROLE")
        return {
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
            "movements": db.execute(
                "SELECT * FROM public.stock_movements "
                "WHERE product_id=%s OR sale_id=%s ORDER BY id",
                (case["product_id"], case["sale_id"]),
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
            "register": db.execute(
                "SELECT * FROM public.register_log WHERE id=%s", (case["register_id"],),
            ).fetchall(),
        }


def cancel(db, case, reason="Venda incorreta"):
    return db.execute(
        "SELECT public.fn_cancel_sale(%s,%s)", (case["sale_id"], reason),
    ).fetchone()[0]


def assert_rejected(db, case, error, reason="Venda incorreta", match=None):
    before = state(db, case)
    with pytest.raises(error, match=match), db.transaction():
        cancel(db, case, reason)
    assert state(db, case) == before


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
def test_admin_cancels_and_preserves_commercial_data(db_tx, sale_case, reason):
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
    assert after["register"] == before["register"]
    reversal, = after["reversals"]
    assert reversal[:3] == ("CANCELAMENTO", reason.strip(), sale_case["actor"])
    assert reversal[3] is not None
    if sale_case["status"] == "PENDENTE":
        assert after["movements"] == before["movements"]
        assert before["product"][0][1] == 10
    else:
        # Certifica apenas o mecanismo legado desta tarefa, não entradas US15.
        assert before["product"][0][1] == 8
        assert len(after["movements"]) == len(before["movements"])
        assert db_tx.execute(
            "SELECT status::text FROM public.stock_movements WHERE sale_id=%s",
            (sale_case["sale_id"],),
        ).fetchall() == [("CANCELADA",)]


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
        match="pendente possui movimentação confirmada",
    )


def test_closed_register_rejection_rolls_back_cancellation(db_tx, sale_case):
    declared = 40 if sale_case["status"] == "CONCLUIDA" else 0
    db_tx.execute(
        "SELECT public.fn_close_register_session(%s,%s)",
        (sale_case["register_id"], declared),
    )
    assert_rejected(db_tx, sale_case, psycopg.Error, match="caixa fechado")


def test_late_failure_rolls_back_audit_stock_and_sale(db_tx, sale_case):
    # DDL exclusivamente no banco descartável, desfeito pela fixture db_tx.
    # O trigger comprova que a auditoria já foi escrita antes da falha injetada.
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
                    SELECT 1 FROM public.stock_movements sm
                    WHERE sm.sale_id=OLD.id AND sm.status='CONFIRMADA'
                ) THEN
                    RAISE EXCEPTION 'Reversão legada não ocorreu antes da falha'
                        USING ERRCODE='XX000';
                END IF;
                RAISE EXCEPTION 'Falha US15 após auditoria' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER zz_us15_test_reject_cancel BEFORE UPDATE OF status ON public.sales
        FOR EACH ROW EXECUTE FUNCTION public.us15_test_reject_cancel();
    """)
    db_tx.execute("SET LOCAL ROLE authenticated")
    assert_rejected(
        db_tx, sale_case, psycopg.errors.CheckViolation, match="Falha US15 após auditoria",
    )


def test_cancellation_execution_grants(db_tx, create_company):
    # create_company também garante que schema/migrations foram preparados.
    for role, allowed in (("anon", False), ("authenticated", True), ("app_backend", True)):
        assert db_tx.execute(
            "SELECT has_function_privilege(%s,'public.fn_cancel_sale(uuid,text)','EXECUTE')",
            (role,),
        ).fetchone()[0] is allowed
