from decimal import Decimal
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
import pytest


def _seller(db_tx, company_id):
    user_id, auth_id = uuid4(), uuid4()
    email = f"seller{user_id.hex[:10]}@local.invalid"
    db_tx.execute("RESET ROLE")
    db_tx.execute(
        "INSERT INTO auth.users(id,email) VALUES (%s,%s)",
        (auth_id, email),
    )
    db_tx.execute(
        "INSERT INTO public.user_accounts(id,name,pass_hash,auth_user_id) "
        "VALUES (%s,%s,'$auth$local-disabled-credential',%s)",
        (user_id, email, auth_id),
    )
    db_tx.execute(
        "INSERT INTO public.company_users(company_id,user_account_id,role) "
        "VALUES (%s,%s,'SELLER')",
        (company_id, user_id),
    )
    db_tx.execute("SET LOCAL ROLE authenticated")
    db_tx.execute(
        "SELECT set_config('request.jwt.claim.sub', %s, true)",
        (str(auth_id),),
    )
    return user_id, auth_id


def _client(db_tx, company_id):
    client_id = uuid4()
    db_tx.execute("RESET ROLE")
    db_tx.execute(
        "INSERT INTO public.clients(id,company_id,name) "
        "VALUES (%s,%s,'Cliente US22')",
        (client_id, company_id),
    )
    db_tx.execute("SET LOCAL ROLE authenticated")
    return client_id


def _register_discounted_sale(db_tx, company_id, client_id, product_code,
                              discount_value, seller_id):
    return db_tx.execute(
        "SELECT public.fn_register_sale_with_discounts("
        "%s,%s,%s,'DINHEIRO'::public.payment_method,'FIXED',%s,%s)",
        (
            company_id,
            client_id,
            Jsonb([{
                "product_code": product_code,
                "quantity": 1,
                "discount_type": "FIXED",
                "discount_value": "0",
            }]),
            discount_value,
            seller_id,
        ),
    ).fetchone()[0]


def test_seller_limit_applies_to_fixed_discount_and_rejects_excess(
    db_tx, create_company, create_product
):
    company_id = create_company
    product_id = create_product(stock=10)
    product_code = db_tx.execute(
        "SELECT barcode FROM public.products WHERE id=%s", (product_id,)
    ).fetchone()[0]
    client_id = _client(db_tx, company_id)
    seller_id, _ = _seller(db_tx, company_id)

    receipt = _register_discounted_sale(
        db_tx, company_id, client_id, product_code, Decimal("2.00"), seller_id
    )
    assert Decimal(str(receipt["original_total"])) == Decimal("20.00")
    assert Decimal(str(receipt["discount"])) == Decimal("2.00")
    assert Decimal(str(receipt["total"])) == Decimal("18.00")
    assert receipt["discount_authorized_by"] is None

    sales_before = db_tx.execute(
        "SELECT count(*) FROM public.sales WHERE company_id=%s", (company_id,)
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with db_tx.transaction():
            _register_discounted_sale(
                db_tx, company_id, client_id, product_code,
                Decimal("2.01"), seller_id,
            )
    assert db_tx.execute(
        "SELECT count(*) FROM public.sales WHERE company_id=%s", (company_id,)
    ).fetchone()[0] == sales_before


def test_admin_approval_is_reauthenticated_and_audited(
    db_tx, create_company, create_product
):
    company_id = create_company
    product_id = create_product(stock=10)
    product_code = db_tx.execute(
        "SELECT barcode FROM public.products WHERE id=%s", (product_id,)
    ).fetchone()[0]
    client_id = _client(db_tx, company_id)
    seller_id, _ = _seller(db_tx, company_id)

    db_tx.execute("RESET ROLE")
    admin_id = db_tx.execute(
        "SELECT cu.user_account_id FROM public.company_users cu "
        "WHERE cu.company_id=%s AND cu.role='ADMIN' AND cu.active",
        (company_id,),
    ).fetchone()[0]
    admin_auth_id = db_tx.execute(
        "SELECT auth_user_id FROM public.user_accounts WHERE id=%s",
        (admin_id,),
    ).fetchone()[0]
    db_tx.execute("SET LOCAL ROLE authenticated")
    db_tx.execute(
        "SELECT set_config('request.jwt.claim.sub', %s, true)",
        (str(admin_auth_id),),
    )

    receipt = _register_discounted_sale(
        db_tx, company_id, client_id, product_code, Decimal("3.00"), seller_id
    )
    assert receipt["discount_applied_by"] == str(seller_id)
    assert receipt["discount_authorized_by"] == str(admin_id)
    assert receipt["discount_authorized_by_name"]
    assert Decimal(str(receipt["discount"])) == Decimal("3.00")
