"""Integração real e isolada; STOCKFLOW_TEST_DSN deve apontar ao PostgreSQL local."""
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def _temporary_backend_role(control, runner):
    """Autoriza SET local para os testes, sem escrita, ADMIN ou INHERIT novos.

    Em PostgreSQL 16+ cada grantor pode ter uma associação própria. Não revogar
    uma associação preexistente de outro grantor ao remover a concessão de teste.
    O papel app_backend já foi criado pelo schema/migrations neste momento.
    """
    if control.info.server_version < 160000:
        if not control.execute(
            "SELECT pg_has_role(current_user,'app_backend','MEMBER')",
        ).fetchone()[0]:
            raise RuntimeError("SET temporário sem INHERIT exige PostgreSQL 16 ou superior")
        yield
        return

    def memberships():
        return control.execute(
            "SELECT grantor::regrole::text,admin_option,inherit_option,set_option "
            "FROM pg_auth_members WHERE roleid='app_backend'::regrole "
            "AND member=(SELECT oid FROM pg_roles WHERE rolname=current_user) ORDER BY grantor",
        ).fetchall()

    before = memberships()
    if control.execute(
        "SELECT pg_has_role(current_user,'app_backend','SET')",
    ).fetchone()[0]:
        # Um contexto externo ou a configuração original já permite SET.
        yield
        return
    own = next((row for row in before if row[0] == runner), None)
    inherit = own[2] if own is not None else False
    grant = sql.SQL(
        "GRANT app_backend TO {} WITH INHERIT {}, SET TRUE GRANTED BY {}"
    ).format(sql.Identifier(runner), sql.SQL("TRUE" if inherit else "FALSE"), sql.Identifier(runner))
    control.execute(grant)
    try:
        assert control.execute(
            "SELECT pg_has_role(current_user,'app_backend','SET')",
        ).fetchone()[0], "O executor não conseguiu assumir app_backend"
        yield
    finally:
        if own is None:
            control.execute(sql.SQL(
                "REVOKE app_backend FROM {} GRANTED BY {}"
            ).format(sql.Identifier(runner), sql.Identifier(runner)))
        else:
            control.execute(sql.SQL(
                "GRANT app_backend TO {} WITH INHERIT {}, SET {} GRANTED BY {}"
            ).format(
                sql.Identifier(runner), sql.SQL("TRUE" if own[2] else "FALSE"),
                sql.SQL("TRUE" if own[3] else "FALSE"), sql.Identifier(runner),
            ))
        if memberships() != before:
            raise RuntimeError("A associação app_backend não retornou ao estado anterior")


@contextmanager
def _stock_database(mode, *, through_migration=None):
    """Banco local isolado; corte inclusivo para testar upgrades com dados reais."""
    if mode not in {"schema", "migrations"}:
        raise ValueError("Modo de banco de teste inválido")
    if through_migration is not None and mode != "migrations":
        raise ValueError("Corte de migrations exige o modo migrations")
    files = (
        [path for group in ("tables", "procedures", "views", "triggers", "policies")
         for path in sorted((ROOT / "database/code" / group).glob("*.sql"))]
        if mode == "schema"
        else sorted((ROOT / "database/supabase/migrations").glob("*.sql"))
    )
    if through_migration is not None:
        names = [path.name for path in files]
        if through_migration not in names:
            raise ValueError("Migration de corte não encontrada")
        files = files[:names.index(through_migration) + 1]
    dsn = os.environ.get("STOCKFLOW_TEST_DSN")
    if not dsn:
        pytest.skip("Defina STOCKFLOW_TEST_DSN para executar contra PostgreSQL local")
    connection_info = conninfo_to_dict(dsn)
    if (connection_info.get("host") not in {"127.0.0.1", "localhost", "::1"}
            or connection_info.get("hostaddr") not in {None, "127.0.0.1", "::1"}):
        pytest.fail("Integração aceita somente um servidor PostgreSQL local descartável")
    name = "stockflow_test_" + uuid4().hex[:12]
    granted_roles = []
    restore_set_option = []
    with psycopg.connect(dsn, autocommit=True) as control:
        runner = control.execute("SELECT current_user").fetchone()[0]
        server_version = control.info.server_version
        for role in ("anon", "authenticated", "service_role"):
            if not control.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                control.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
            if server_version >= 160000:
                membership = control.execute(
                    """
                    SELECT set_option
                      FROM pg_auth_members
                     WHERE roleid = %s::regrole
                       AND member = (SELECT oid FROM pg_roles WHERE rolname = current_user)
                    """,
                    (role,),
                ).fetchone()
                if membership is None:
                    control.execute(
                        sql.SQL("GRANT {} TO {} WITH SET TRUE").format(
                            sql.Identifier(role), sql.Identifier(runner),
                        )
                    )
                    granted_roles.append(role)
                elif not membership[0]:
                    control.execute(
                        sql.SQL("GRANT {} TO {} WITH SET TRUE").format(
                            sql.Identifier(role), sql.Identifier(runner),
                        )
                    )
                    restore_set_option.append(role)
            elif not control.execute(
                "SELECT pg_has_role(current_user, %s, 'MEMBER')", (role,),
            ).fetchone()[0]:
                control.execute(
                    sql.SQL("GRANT {} TO {}").format(
                        sql.Identifier(role), sql.Identifier(runner),
                    )
                )
                granted_roles.append(role)
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
                if mode == "migrations":
                    setup.execute("""
                        CREATE SCHEMA extensions;
                        CREATE EXTENSION pgcrypto WITH SCHEMA extensions;
                    """)
                for path in files:
                    try:
                        setup.execute(path.read_text())
                    except psycopg.Error as error:
                        error.add_note(f"SQL file: {path.relative_to(ROOT)}")
                        raise
            with _temporary_backend_role(control, runner):
                yield target
        finally:
            try:
                control.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            finally:
                # Restaurar associações mesmo se uma sessão externa impedir o DROP.
                # Não conceder pg_signal_backend nem ocultar falhas de limpeza.
                for role in granted_roles:
                    control.execute(
                        sql.SQL("REVOKE {} FROM {}").format(
                            sql.Identifier(role), sql.Identifier(runner),
                        )
                    )
                for role in restore_set_option:
                    control.execute(
                        sql.SQL("GRANT {} TO {} WITH SET FALSE").format(
                            sql.Identifier(role), sql.Identifier(runner),
                        )
                    )


@pytest.fixture(scope="session")
def stock_database_factory():
    """O chamador fecha as conexões antes de sair do contexto e remover o banco."""
    return _stock_database


@pytest.fixture(scope="session", params=("schema", "migrations"))
def stock_database(request, stock_database_factory):
    with stock_database_factory(request.param) as target:
        yield target


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
