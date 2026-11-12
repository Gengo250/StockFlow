import json

import psycopg
import pytest


def create_supplier(db_tx, company_id):
    return db_tx.execute(
        "SELECT fn_create_supplier(%s, 'Fornecedor de teste')", (company_id,)
    ).fetchone()[0]


def create_purchase(db_tx, company_id, supplier_id, items):
    return db_tx.execute(
        "SELECT fn_create_purchase(%s, %s, %s::jsonb)",
        (company_id, supplier_id, json.dumps(items)),
    ).fetchone()[0]


def product_code(db_tx, product_id):
    return db_tx.execute(
        "SELECT barcode FROM products WHERE id=%s", (product_id,)
    ).fetchone()[0]


def test_receiving_adds_one_confirmed_supplier_movement_per_item(
    db_tx, create_company, create_product
):
    supplier = create_supplier(db_tx, create_company)
    first = create_product(stock=3)
    second = create_product(stock=5)
    first_code = product_code(db_tx, first)
    second_code = product_code(db_tx, second)
    purchase = create_purchase(
        db_tx,
        create_company,
        supplier,
        [
            {"product_code": first_code, "quantity": 2},
            {"product_code": second_code, "quantity": 4},
        ],
    )

    db_tx.execute("SELECT fn_receive_purchase(%s)", (purchase,))

    assert db_tx.execute(
        "SELECT status::text, received_on IS NOT NULL FROM purchases WHERE id=%s",
        (purchase,),
    ).fetchone() == ("RECEBIDA", True)
    balances = db_tx.execute(
        "SELECT id, stock FROM products WHERE id IN (%s, %s) ORDER BY barcode",
        (first, second),
    ).fetchall()
    assert dict(balances) == {first: 5, second: 9}
    assert db_tx.execute(
        """
        SELECT count(*)
          FROM stock_movements
         WHERE purchase_id=%s AND supplier_id=%s
           AND kind='ENTRADA' AND status='CONFIRMADA'
        """,
        (purchase, supplier),
    ).fetchone()[0] == 2


def test_duplicate_receipt_is_rejected_without_more_movements(
    db_tx, create_company, create_product
):
    supplier = create_supplier(db_tx, create_company)
    product = create_product(stock=1)
    code = product_code(db_tx, product)
    purchase = create_purchase(
        db_tx, create_company, supplier,
        [{"product_code": code, "quantity": 2}],
    )
    db_tx.execute("SELECT fn_receive_purchase(%s)", (purchase,))

    with pytest.raises(psycopg.Error, match="rascunho"):
        with db_tx.transaction():
            db_tx.execute("SELECT fn_receive_purchase(%s)", (purchase,))

    assert db_tx.execute(
        "SELECT stock FROM products WHERE id=%s", (product,)
    ).fetchone()[0] == 3
    assert db_tx.execute(
        "SELECT count(*) FROM stock_movements WHERE purchase_id=%s", (purchase,)
    ).fetchone()[0] == 1


def test_any_item_failure_rolls_back_movements_stock_and_purchase_status(
    db_tx, create_company, create_product
):
    supplier = create_supplier(db_tx, create_company)
    first = create_product(stock=3)
    constrained = create_product(stock=10, maximum=10)
    first_code = product_code(db_tx, first)
    constrained_code = product_code(db_tx, constrained)
    purchase = create_purchase(
        db_tx, create_company, supplier,
        [
            {"product_code": first_code, "quantity": 2},
            {"product_code": constrained_code, "quantity": 1},
        ],
    )

    with pytest.raises(psycopg.Error, match="estoque máximo"):
        with db_tx.transaction():
            db_tx.execute("SELECT fn_receive_purchase(%s)", (purchase,))

    assert db_tx.execute(
        "SELECT status::text, received_on FROM purchases WHERE id=%s", (purchase,)
    ).fetchone() == ("RASCUNHO", None)
    balances = db_tx.execute(
        "SELECT id, stock FROM products WHERE id IN (%s, %s) ORDER BY barcode",
        (first, constrained),
    ).fetchall()
    assert dict(balances) == {first: 3, constrained: 10}
    assert db_tx.execute(
        "SELECT count(*) FROM stock_movements WHERE purchase_id=%s", (purchase,)
    ).fetchone()[0] == 0
