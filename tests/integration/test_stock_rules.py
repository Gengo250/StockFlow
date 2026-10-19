"""Regras de teto verificadas com SQL, RLS e gatilhos reais nos dois schemas."""
import psycopg
import pytest


def test_set_max_stock_respects_company_limit(db_tx, create_product):
    product = create_product()
    with pytest.raises(psycopg.errors.CheckViolation, match="excede"):
        with db_tx.transaction():
            db_tx.execute("SELECT fn_set_max_stock(%s,15000)", (product,))
    assert db_tx.execute("SELECT max_quantity FROM product_stock WHERE product_id=%s", (product,)).fetchone()[0] is None


def test_max_cannot_be_less_than_current_stock(db_tx, create_product):
    product = create_product(stock=400)
    with pytest.raises(psycopg.errors.CheckViolation, match="saldo"):
        db_tx.execute("SELECT fn_set_max_stock(%s,300)", (product,))


def test_set_company_max_stock_limit_ok(db_tx, create_company):
    db_tx.execute("SELECT fn_set_company_max_stock_limit(%s,25000)", (create_company,))
    assert db_tx.execute("SELECT max_stock_limit FROM company WHERE id=%s", (create_company,)).fetchone()[0] == 25000


def test_set_company_max_stock_limit_negative(db_tx, create_company):
    with pytest.raises(psycopg.errors.CheckViolation, match="maior ou igual a zero"):
        db_tx.execute("SELECT fn_set_company_max_stock_limit(%s,-100)", (create_company,))


def test_set_company_max_stock_limit_blocked_by_product_max(db_tx, create_company, create_product):
    create_product(maximum=5000)
    with pytest.raises(psycopg.errors.CheckViolation, match="produtos com estoque máximo superior"):
        db_tx.execute("SELECT fn_set_company_max_stock_limit(%s,3000)", (create_company,))


def test_get_effective_max_stock_uses_product_max(db_tx, create_product):
    product = create_product(stock=10, minimum=5, maximum=80)
    assert db_tx.execute("SELECT fn_get_effective_max_stock(%s)", (product,)).fetchone()[0] == 80


def test_get_effective_max_stock_uses_company_limit(db_tx, create_company, create_product):
    product = create_product(stock=10, minimum=5)
    limit = db_tx.execute("SELECT max_stock_limit FROM company WHERE id=%s", (create_company,)).fetchone()[0]
    assert db_tx.execute("SELECT fn_get_effective_max_stock(%s)", (product,)).fetchone()[0] == limit


def test_movement_exceeds_max_fails(db_tx, create_company, create_product):
    product = create_product(stock=20, minimum=5, maximum=50)
    before = db_tx.execute("SELECT count(*) FROM stock_movements WHERE product_id=%s", (product,)).fetchone()[0]
    with pytest.raises(psycopg.errors.CheckViolation, match="máximo"):
        with db_tx.transaction():
            db_tx.execute("SELECT fn_register_movement(%s,%s,'ENTRADA',40,p_confirm => true)", (create_company, product))
    assert db_tx.execute("SELECT stock FROM products WHERE id=%s", (product,)).fetchone()[0] == 20
    assert db_tx.execute("SELECT count(*) FROM stock_movements WHERE product_id=%s", (product,)).fetchone()[0] == before


def test_set_max_stock_happy_path(db_tx, create_product):
    product = create_product(stock=30)
    db_tx.execute("SELECT fn_set_max_stock(%s,500)", (product,))
    assert db_tx.execute("SELECT max_quantity FROM product_stock WHERE product_id=%s", (product,)).fetchone()[0] == 500


def test_effective_limit_does_not_leak_another_company(db_tx, create_product):
    product = create_product(maximum=500)
    db_tx.execute("SELECT set_config('request.jwt.claim.sub', '', true)")
    assert db_tx.execute("SELECT fn_get_effective_max_stock(%s)", (product,)).fetchone()[0] is None
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db_tx.execute("SELECT fn_set_max_stock(%s,600)", (product,))


def test_minimum_can_be_cleared(db_tx, create_product):
    product = create_product()
    db_tx.execute("SELECT fn_set_min_stock(%s,NULL)", (product,))
    assert db_tx.execute("SELECT min_quantity FROM product_stock WHERE product_id=%s", (product,)).fetchone()[0] is None


def test_product_form_without_minimum_and_invalid_maximum_is_atomic(db_tx, create_company):
    from psycopg.types.json import Jsonb
    data = dict(code="ATOMIC", name="Produto", unit="UN", sale_price="10", cost="5",
                stock="30", minimum_stock=None, maximum_stock=20)
    with pytest.raises(psycopg.errors.CheckViolation, match="saldo"):
        with db_tx.transaction():
            db_tx.execute("SELECT fn_save_product(%s,NULL,%s)", (create_company, Jsonb(data)))
    assert db_tx.execute("SELECT count(*) FROM products WHERE barcode='ATOMIC'").fetchone()[0] == 0
    assert db_tx.execute("SELECT count(*) FROM stock_movements").fetchone()[0] == 0
    data["maximum_stock"] = 50
    product = db_tx.execute("SELECT fn_save_product(%s,NULL,%s)", (create_company, Jsonb(data))).fetchone()[0]
    assert db_tx.execute("SELECT min_quantity,max_quantity FROM product_stock WHERE product_id=%s", (product,)).fetchone() == (None, 50)
    data.update(minimum_stock=60, maximum_stock=100)
    db_tx.execute("SELECT fn_save_product(%s,%s,%s)", (create_company, product, Jsonb(data)))
    assert db_tx.execute("SELECT min_quantity,max_quantity FROM product_stock WHERE product_id=%s", (product,)).fetchone() == (60, 100)


def test_anonymous_cannot_call_stock_limit_functions(db_tx, create_product):
    product = create_product()
    db_tx.execute("RESET ROLE")
    db_tx.execute("SET LOCAL ROLE anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db_tx.execute("SELECT fn_get_effective_max_stock(%s)", (product,))
