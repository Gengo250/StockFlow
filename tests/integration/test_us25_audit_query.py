"""Permissão da consulta US25 no schema declarativo e nas migrations."""
from uuid import uuid4

import psycopg
import pytest


def test_admin_can_call_audit_query(db_tx, create_company):
    assert db_tx.execute(
        "SELECT * FROM public.fn_list_audit_events(%s)", (create_company,),
    ).fetchall() == []


@pytest.mark.parametrize("role", ["SELLER", "STOCK"])
def test_audit_query_checks_profile_after_execute_permission(db_tx, create_company, role):
    user, auth = uuid4(), uuid4()
    db_tx.execute("RESET ROLE")
    db_tx.execute("INSERT INTO auth.users(id,email) VALUES (%s,%s)", (auth, f"{auth}@local.invalid"))
    db_tx.execute(
        "INSERT INTO user_accounts(id,name,pass_hash,auth_user_id) "
        "VALUES (%s,%s,'$auth$local-disabled-credential',%s)",
        (user, str(user), auth),
    )
    db_tx.execute(
        "INSERT INTO company_users(company_id,user_account_id,role) VALUES (%s,%s,%s)",
        (create_company, user, role),
    )
    db_tx.execute("SET LOCAL ROLE authenticated")
    db_tx.execute("SELECT set_config('request.jwt.claim.sub', %s, true)", (str(auth),))
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="Apenas administradores"), db_tx.transaction():
        db_tx.execute("SELECT * FROM public.fn_list_audit_events(%s)", (create_company,))


def test_anonymous_cannot_call_audit_query(db_tx, create_company):
    db_tx.execute("RESET ROLE")
    db_tx.execute("SET LOCAL ROLE anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db_tx.transaction():
        db_tx.execute("SELECT * FROM public.fn_list_audit_events(%s)", (create_company,))
