"""Integração real e isolada; STOCKFLOW_TEST_DSN deve apontar ao PostgreSQL local."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", params=("schema", "migrations"))
def stock_database(request):
    dsn = os.environ.get("STOCKFLOW_TEST_DSN")
    if not dsn:
        pytest.skip("Defina STOCKFLOW_TEST_DSN para executar contra PostgreSQL local")
    if conninfo_to_dict(dsn).get("host") not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("Integração aceita somente um servidor PostgreSQL local descartável")
    name = "stockflow_test_" + uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as control:
        for role in ("anon", "authenticated", "service_role"):
            if not control.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                control.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        control.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        target = make_conninfo(dsn, dbname=name)
        try:
            with psycopg.connect(target, autocommit=True) as setup:
                setup.execute("""
                    CREATE SCHEMA auth;
                    CREATE TABLE auth.users(id uuid PRIMARY KEY, email varchar(255),
                        raw_user_meta_data jsonb DEFAULT '{}', last_sign_in_at timestamptz);
                    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
                        SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
                    GRANT USAGE ON SCHEMA auth TO authenticated, anon;
                    GRANT EXECUTE ON FUNCTION auth.uid() TO authenticated, anon;
                """)
                files = (
                    [path for group in ("tables", "procedures", "views", "triggers", "policies")
                     for path in sorted((ROOT / "database/code" / group).glob("*.sql"))]
                    if request.param == "schema"
                    else sorted((ROOT / "database/supabase/migrations").glob("*.sql"))
                )
                for path in files:
                    try:
                        setup.execute(path.read_text())
                    except psycopg.Error as error:
                        error.add_note(f"SQL file: {path.relative_to(ROOT)}")
                        raise
            yield target
        finally:
            control.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def db_tx(stock_database):
    with psycopg.connect(stock_database, autocommit=True) as connection:
        with connection.transaction(force_rollback=True):
            yield connection


@pytest.fixture
def create_company(db_tx):
    company, user, auth = (uuid4() for _ in range(3))
    db_tx.execute("INSERT INTO company(id,name) VALUES (%s,'Empresa teste')", (company,))
    db_tx.execute("INSERT INTO auth.users(id,email) VALUES (%s,'admin@local.invalid')", (auth,))
    db_tx.execute("INSERT INTO user_accounts(id,name,pass_hash,auth_user_id) VALUES (%s,'admin@local.invalid','$auth$local-disabled-credential',%s)", (user, auth))
    db_tx.execute("INSERT INTO company_users(company_id,user_account_id,role) VALUES (%s,%s,'ADMIN')", (company, user))
    db_tx.execute("SET LOCAL ROLE authenticated")
    db_tx.execute("SELECT set_config('request.jwt.claim.sub', %s, true)", (str(auth),))
    return company


@pytest.fixture
def create_product(db_tx, create_company):
    def create(stock=100, minimum=10, maximum=None):
        # O saldo nasce por movimentação confirmada, como no cadastro da UI.
        product = db_tx.execute(
            "SELECT fn_create_products(%s,%s,'Produto teste',20,p_stock => %s)",
            (create_company, uuid4().hex[:12], stock),
        ).fetchone()[0]
        db_tx.execute("SELECT fn_set_min_stock(%s,%s)", (product, minimum))
        if maximum is not None:
            db_tx.execute("SELECT fn_set_max_stock(%s,%s)", (product, maximum))
        return product
    return create
