from decimal import Decimal

import psycopg
import pytest


def test_current_open_close(db_tx, create_company):
    company = create_company
    assert db_tx.execute('SELECT fn_current_register_session(%s)', (company,)).fetchone()[0] is None
    opened = db_tx.execute('SELECT fn_start_my_register(%s,100)', (company,)).fetchone()[0]
    assert opened['status'] == 'OPEN'
    assert db_tx.execute('SELECT fn_current_register_session(%s)', (company,)).fetchone()[0]['id'] == opened['id']
    with pytest.raises(psycopg.Error), db_tx.transaction():
        db_tx.execute('SELECT fn_start_my_register(%s,0)', (company,))
    with pytest.raises(psycopg.Error, match='justificativa'), db_tx.transaction():
        db_tx.execute('SELECT fn_close_register_session(%s)', (opened['id'],))
    result = db_tx.execute('SELECT fn_close_register_session(%s,100)', (opened['id'],)).fetchone()[0]
    assert result['difference'] == 0
    assert db_tx.execute('SELECT fn_current_register_session(%s)', (company,)).fetchone()[0] is None


def test_anon_cannot_open(db_tx, create_company):
    db_tx.execute('SET LOCAL ROLE anon')
    with pytest.raises(psycopg.Error), db_tx.transaction():
        db_tx.execute('SELECT fn_start_my_register(%s,0)', (create_company,))


def test_sale_resolves_open_register(db_tx, create_company, create_product):
    product = create_product()
    opened = db_tx.execute('SELECT fn_start_my_register(%s,100)', (create_company,)).fetchone()[0]
    # Usar o mesmo INSERT realizado pela RPC; vínculo é resolvido no trigger.
    db_tx.execute('RESET ROLE')
    sale = db_tx.execute("""INSERT INTO sales(company_id, total, created_by, payment_method, status, client_name)
        VALUES (%s,20,fn_current_user_id(),'PIX','CONCLUIDA','Cliente teste') RETURNING register_log_id""", (create_company,)).fetchone()[0]
    assert str(sale) == opened['id']
    db_tx.execute('SET LOCAL ROLE authenticated')
    result = db_tx.execute('SELECT fn_close_register_session(%s,100,0,0,20)', (opened['id'],)).fetchone()[0]
    assert result['total_expected'] == 120


@pytest.mark.parametrize('value', [-1, Decimal('NaN'), Decimal('0.001')])
def test_rejects_invalid_balance(db_tx, create_company, value):
    with pytest.raises(psycopg.Error), db_tx.transaction():
        db_tx.execute('SELECT fn_start_my_register(%s,%s)', (create_company, value))
    assert db_tx.execute('SELECT fn_current_register_session(%s)', (create_company,)).fetchone()[0] is None


def test_other_operator_cannot_close(db_tx, create_company):
    from uuid import uuid4
    opened = db_tx.execute('SELECT fn_start_my_register(%s,0)', (create_company,)).fetchone()[0]
    db_tx.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (str(uuid4()),))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db_tx.transaction():
        db_tx.execute('SELECT fn_close_register_session(%s)', (opened['id'],))


def test_concurrent_open_only_one_succeeds(stock_database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4
    company, user, auth = uuid4(), uuid4(), uuid4()
    with psycopg.connect(stock_database, autocommit=True) as setup:
        setup.execute("INSERT INTO company(id,name) VALUES (%s,'Concorrência caixa')", (company,))
        setup.execute("INSERT INTO auth.users(id,email) VALUES (%s,%s)", (auth, f'{auth}@local.invalid'))
        setup.execute("INSERT INTO user_accounts(id,name,pass_hash,auth_user_id) VALUES (%s,%s,'$auth$local-disabled-credential',%s)", (user, str(user), auth))
        setup.execute("INSERT INTO company_users(company_id,user_account_id,role) VALUES (%s,%s,'SELLER')", (company,user))
    barrier = Barrier(2)
    def start():
        with psycopg.connect(stock_database, autocommit=True) as db:
            db.execute('SET ROLE authenticated')
            db.execute("SELECT set_config('request.jwt.claim.sub',%s,false)", (str(auth),))
            barrier.wait(timeout=5)
            try:
                return db.execute('SELECT fn_start_my_register(%s,0)', (company,)).fetchone()[0]
            except psycopg.Error:
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(), range(2)))
    assert sum(result is not None for result in results) == 1
    with psycopg.connect(stock_database) as db:
        assert db.execute("SELECT count(*) FROM register_log WHERE operator_id=%s AND status='OPEN'", (user,)).fetchone()[0] == 1


def test_stock_role_cannot_start_or_close(db_tx, create_company):
    opened = db_tx.execute('SELECT fn_start_my_register(%s,0)', (create_company,)).fetchone()[0]
    db_tx.execute('RESET ROLE')
    from uuid import uuid4
    backup_admin = uuid4()
    db_tx.execute("INSERT INTO user_accounts(id,name,pass_hash) VALUES (%s,%s,'$auth$local-disabled-credential')", (backup_admin,str(backup_admin)))
    db_tx.execute("INSERT INTO company_users(company_id,user_account_id,role) VALUES (%s,%s,'ADMIN')", (create_company,backup_admin))
    db_tx.execute("UPDATE company_users SET role='STOCK' WHERE company_id=%s AND user_account_id=fn_current_user_id()", (create_company,))
    db_tx.execute('SET LOCAL ROLE authenticated')
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db_tx.transaction():
        db_tx.execute('SELECT fn_start_my_register(%s,0)', (create_company,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db_tx.transaction():
        db_tx.execute('SELECT fn_close_register_session(%s)', (opened['id'],))


def test_sale_cannot_enter_closed_register(db_tx, create_company):
    opened = db_tx.execute('SELECT fn_start_my_register(%s,0)', (create_company,)).fetchone()[0]
    db_tx.execute('SELECT fn_close_register_session(%s)', (opened['id'],))
    db_tx.execute('RESET ROLE')
    with pytest.raises(psycopg.Error, match='caixa fechado'), db_tx.transaction():
        db_tx.execute("""INSERT INTO sales(company_id, total, created_by, payment_method, status, client_name, register_log_id)
            VALUES (%s,20,fn_current_user_id(),'PIX','CONCLUIDA','Teste',%s)""", (create_company,opened['id']))
