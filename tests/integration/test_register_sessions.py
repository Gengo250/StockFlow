from decimal import Decimal
from uuid import uuid4


def test_open_and_close_register_session_persists_the_initial_balance(
    db_tx, create_company
):
    register_id = uuid4()
    db_tx.execute("RESET ROLE")
    db_tx.execute("INSERT INTO public.register(id) VALUES (%s)", (register_id,))
    db_tx.execute("SET LOCAL ROLE authenticated")

    operator_id = db_tx.execute(
        "SELECT public.fn_current_user_id()"
    ).fetchone()[0]
    log_id = db_tx.execute(
        "SELECT public.fn_open_register_session(%s,%s,%s,NULL,%s)",
        (create_company, register_id, operator_id, Decimal("125.00")),
    ).fetchone()[0]

    db_tx.execute("RESET ROLE")
    register = db_tx.execute(
        "SELECT change, session_id FROM public.register WHERE id=%s",
        (register_id,),
    ).fetchone()
    assert register[0] == Decimal("125.00")
    assert register[1] is None

    db_tx.execute("SET LOCAL ROLE authenticated")
    result = db_tx.execute(
        "SELECT public.fn_close_register_session(%s, %s)",
        (log_id, Decimal("125.00")),
    ).fetchone()[0]

    assert result["status"] == "CLOSED"
    assert Decimal(str(result["initial_balance"])) == Decimal("125.00")
    assert Decimal(str(result["total_expected"])) == Decimal("125.00")
    assert Decimal(str(result["difference"])) == Decimal("0.00")

    db_tx.execute("RESET ROLE")
    assert db_tx.execute(
        "SELECT session_id FROM public.register WHERE id=%s",
        (register_id,),
    ).fetchone()[0] is None
    assert db_tx.execute(
        "SELECT status, closed_at IS NOT NULL FROM public.register_log WHERE id=%s",
        (log_id,),
    ).fetchone() == ("CLOSED", True)


def test_seller_can_open_and_close_their_own_register_session(
    db_tx, create_company
):
    seller_id, auth_id, register_id = uuid4(), uuid4(), uuid4()
    db_tx.execute("RESET ROLE")
    db_tx.execute(
        "INSERT INTO auth.users(id,email) VALUES (%s,%s)",
        (auth_id, f"seller-{auth_id.hex[:10]}@local.invalid"),
    )
    db_tx.execute(
        "INSERT INTO public.user_accounts(id,name,pass_hash,auth_user_id) "
        "VALUES (%s,%s,'$auth$local-disabled-credential',%s)",
        (seller_id, f"seller-{auth_id.hex[:10]}@local.invalid", auth_id),
    )
    db_tx.execute(
        "INSERT INTO public.company_users(company_id,user_account_id,role) "
        "VALUES (%s,%s,'SELLER')",
        (create_company, seller_id),
    )
    db_tx.execute("INSERT INTO public.register(id) VALUES (%s)", (register_id,))
    db_tx.execute("SET LOCAL ROLE authenticated")
    db_tx.execute(
        "SELECT set_config('request.jwt.claim.sub', %s, true)",
        (str(auth_id),),
    )

    log_id = db_tx.execute(
        "SELECT public.fn_open_register_session(%s,%s,%s,NULL,%s)",
        (create_company, register_id, seller_id, Decimal("40.00")),
    ).fetchone()[0]
    result = db_tx.execute(
        "SELECT public.fn_close_register_session(%s,%s)",
        (log_id, Decimal("40.00")),
    ).fetchone()[0]

    assert result["status"] == "CLOSED"
    assert Decimal(str(result["initial_balance"])) == Decimal("40.00")
