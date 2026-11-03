"""Acceptance probes; run only against a disposable localhost PostgreSQL.

Reuses the repository's schema/migrations fixtures. Failures are findings,
not xfails: production code is deliberately unchanged.
"""
import importlib.util
from pathlib import Path
from uuid import uuid4
from decimal import Decimal

import pytest
import psycopg
from psycopg.types.json import Jsonb
from concurrent.futures import ThreadPoolExecutor
import time

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("audit_db_fixtures", ROOT / "tests/integration/conftest.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
stock_database = fixtures.stock_database
db_tx = fixtures.db_tx
create_company = fixtures.create_company
create_product = fixtures.create_product


def cash_available(db):
    if not db.execute("SELECT to_regclass('public.register_log')").fetchone()[0]:
        pytest.skip("US23 absent from declarative schema")


def open_cash(db, company):
    cash_available(db)
    db.execute("RESET ROLE")
    register = db.execute("INSERT INTO register DEFAULT VALUES RETURNING id").fetchone()[0]
    actor = db.execute("SELECT fn_current_user_id()").fetchone()[0]
    log = db.execute("SELECT fn_open_register_session(%s,%s,%s,NULL,0)", (company, register, actor)).fetchone()[0]
    db.execute("SET LOCAL ROLE authenticated")
    return log


def sale(db, company, product, quantity=2):
    code = db.execute("SELECT barcode FROM products WHERE id=%s", (product,)).fetchone()[0]
    client = db.execute("SELECT fn_create_client(%s,'Audit client')", (company,)).fetchone()[0]
    return db.execute(
        "SELECT fn_register_sale_with_discounts(%s,%s,%s,'DINHEIRO','FIXED',0,fn_current_user_id())",
        (company, client, Jsonb([dict(product_code=code, quantity=quantity, discount_type='FIXED', discount_value='0')])),
    ).fetchone()[0]


def test_cash_schema_parity(db_tx):
    assert db_tx.execute("SELECT to_regclass('public.register_log')").fetchone()[0], "US23 missing in declarative schema"


def test_checkout_works_with_open_cash(db_tx, create_company, create_product):
    product = create_product(stock=10)
    open_cash(db_tx, create_company)
    result = sale(db_tx, create_company, product)
    assert Decimal(str(result['total'])) == Decimal('40')


def test_anonymous_cannot_open_cash(db_tx, create_company):
    cash_available(db_tx)
    db_tx.execute("RESET ROLE")
    register = db_tx.execute("INSERT INTO register DEFAULT VALUES RETURNING id").fetchone()[0]
    db_tx.execute("SET LOCAL ROLE anon")
    db_tx.execute("SELECT set_config('request.jwt.claim.sub', '', true)")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with db_tx.transaction():
            db_tx.execute("SELECT fn_open_register_session(%s,%s,%s,NULL,0)", (create_company, register, uuid4()))


def test_anonymous_cannot_close_cash(db_tx, create_company):
    log = open_cash(db_tx, create_company)
    db_tx.execute("SET LOCAL ROLE anon")
    db_tx.execute("SELECT set_config('request.jwt.claim.sub', '', true)")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with db_tx.transaction():
            db_tx.execute("SELECT fn_close_register_session(%s)", (log,))


def test_closed_session_is_immutable(db_tx, create_company):
    log = open_cash(db_tx, create_company)
    db_tx.execute("SELECT fn_close_register_session(%s)", (log,))
    # No direct mutation of financial history should be available to a user.
    with pytest.raises(psycopg.Error):
        with db_tx.transaction():
            db_tx.execute("UPDATE register_log SET initial_balance=999 WHERE id=%s", (log,))


def test_duplicate_open_session_rejected(db_tx, create_company):
    open_cash(db_tx, create_company)
    with pytest.raises(psycopg.Error, match='simultaneamente'):
        with db_tx.transaction():
            open_cash(db_tx, create_company)


def test_cash_difference_requires_reason(db_tx, create_company):
    log = open_cash(db_tx, create_company)
    with pytest.raises(psycopg.Error, match='justificativa'):
        with db_tx.transaction():
            db_tx.execute("SELECT fn_close_register_session(%s,5)", (log,))
    result = db_tx.execute("SELECT fn_close_register_session(%s,5,p_justification=>'audit discrepancy')", (log,)).fetchone()[0]
    assert result['difference'] == 5 and result['status'] == 'CLOSED'


def test_partial_return_stock_amount_and_idempotency(db_tx, create_company, create_product):
    product = create_product(stock=10)
    # Migrations should also support this via their public checkout RPC.
    if db_tx.execute("SELECT to_regclass('public.register_log')").fetchone()[0]:
        open_cash(db_tx, create_company)
    result = sale(db_tx, create_company, product)
    sale_id = result['id']
    item = db_tx.execute("SELECT id FROM sale_items WHERE sale_id=%s", (sale_id,)).fetchone()[0]
    args = (sale_id, Jsonb([dict(sale_item_id=str(item), quantity=1)]), uuid4())
    first = db_tx.execute("SELECT fn_return_partial_sale(%s,%s,'audit',%s)", args).fetchone()[0]
    again = db_tx.execute("SELECT fn_return_partial_sale(%s,%s,'audit',%s)", args).fetchone()[0]
    assert first == again
    assert Decimal(str(first['total_amount'])) == Decimal('20')
    assert db_tx.execute("SELECT stock FROM products WHERE id=%s", (product,)).fetchone()[0] == 9
    with pytest.raises(psycopg.Error):
        with db_tx.transaction():
            db_tx.execute("SELECT fn_return_partial_sale(%s,%s,'audit',%s)", (sale_id, Jsonb([dict(sale_item_id=str(item), quantity=2)]), uuid4()))


def test_receipt_rejects_inconsistent_payment_total():
    from stockflow.domain.sale_receipt import build_sale_receipt, ReceiptCompany, ReceiptNotAvailable
    row = dict(id='audit', status='CONCLUIDA', original_total='100', total='1', discount='0',
               items=[dict(product_code='P1', product_name='Audit', quantity=1, unit_price='100', subtotal='100')])
    with pytest.raises(ReceiptNotAvailable):
        build_sale_receipt(row, ReceiptCompany('Audit'))


def test_partial_return_on_seeded_sale(db_tx, create_company, create_product):
    """Isolates US20 from the broken checkout; seed through real triggers."""
    product = create_product(stock=10)
    has_cash = bool(db_tx.execute("SELECT to_regclass('public.register_log')").fetchone()[0])
    log = open_cash(db_tx, create_company) if has_cash else None
    db_tx.execute("RESET ROLE")
    extra_col, extra_val = (",register_log_id", ",%s") if has_cash else ("", "")
    params = (create_company, log) if has_cash else (create_company,)
    sale_id = db_tx.execute(
        f"INSERT INTO sales(company_id,client_name,total,status,created_by{extra_col}) "
        f"VALUES (%s,'Audit',40,'PENDENTE',fn_current_user_id(){extra_val}) RETURNING id", params
    ).fetchone()[0]
    code = db_tx.execute("SELECT barcode FROM products WHERE id=%s", (product,)).fetchone()[0]
    item = db_tx.execute(
        "INSERT INTO sale_items(company_id,sale_id,product_id,product_code,product_name,quantity,unit_price) "
        "VALUES (%s,%s,%s,%s,'Audit',2,20) RETURNING id", (create_company, sale_id, product, code)
    ).fetchone()[0]
    db_tx.execute("UPDATE sales SET status='CONCLUIDA' WHERE id=%s", (sale_id,))
    db_tx.execute("SET LOCAL ROLE authenticated")
    args = (sale_id, Jsonb([dict(sale_item_id=str(item), quantity=1)]), uuid4())
    first = db_tx.execute("SELECT fn_return_partial_sale(%s,%s,'audit',%s)", args).fetchone()[0]
    assert Decimal(str(first['total_amount'])) == Decimal('20')
    assert first == db_tx.execute("SELECT fn_return_partial_sale(%s,%s,'audit',%s)", args).fetchone()[0]
    assert db_tx.execute("SELECT stock FROM products WHERE id=%s", (product,)).fetchone()[0] == 9
    with pytest.raises(psycopg.Error):
        with db_tx.transaction():
            db_tx.execute("SELECT fn_return_partial_sale(%s,%s,'audit',%s)", (sale_id, Jsonb([dict(sale_item_id=str(item), quantity=2)]), uuid4()))
    # Failed over-return must not leave financial or stock records behind.
    assert db_tx.execute("SELECT count(*) FROM returns WHERE sale_id=%s", (sale_id,)).fetchone()[0] == 1
    assert db_tx.execute("SELECT stock FROM products WHERE id=%s", (product,)).fetchone()[0] == 9


def test_concurrent_open_keeps_single_session(stock_database):
    with psycopg.connect(stock_database, autocommit=True) as control:
        cash_available(control)
        company = control.execute("INSERT INTO company(name) VALUES ('Audit concurrency') RETURNING id").fetchone()[0]
        register = control.execute("INSERT INTO register DEFAULT VALUES RETURNING id").fetchone()[0]
        actor = uuid4()
        query = "SELECT fn_open_register_session(%s,%s,%s,NULL,0)"
        args = (company, register, actor)
        with psycopg.connect(stock_database) as first, psycopg.connect(stock_database) as second:
            first.execute(query, args)
            second.execute("SET statement_timeout='5s'")
            pid = second.info.backend_pid
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(second.execute, query, args)
                deadline = time.monotonic() + 3
                blocked = False
                while time.monotonic() < deadline and not future.done():
                    wait = control.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (pid,)).fetchone()
                    if wait and wait[0] == 'Lock':
                        blocked = True
                        break
                    time.sleep(.01)
                first.commit()
                try:
                    future.result()
                    second.commit()
                except psycopg.Error:
                    second.rollback()
                assert blocked, 'Concurrency setup did not overlap transactions'
        count = control.execute("SELECT count(*) FROM register_log WHERE register_id=%s AND status='OPEN'", (register,)).fetchone()[0]
        assert count == 1, f'{count} simultaneous OPEN sessions for the same register/operator'
