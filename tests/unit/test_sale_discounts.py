from decimal import Decimal

import pytest

from stockflow.domain.sale_discount import (
    calculate_discount,
    calculate_discount_breakdown,
)


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [
        ("FIXED", Decimal("3.25"), Decimal("3.25")),
        ("PERCENTAGE", Decimal("12.5"), Decimal("12.50")),
        ("PERCENTAGE", Decimal("12.5"), Decimal("0.13")),
    ],
)
def test_discount_amount_uses_fixed_or_percentage(kind, value, expected):
    base = Decimal("1.00") if expected == Decimal("0.13") else Decimal("100.00")
    assert calculate_discount(base, kind, value) == expected


@pytest.mark.parametrize(
    ("kind", "value"),
    [("FIXED", Decimal("10.01")), ("PERCENTAGE", Decimal("100.01"))],
)
def test_discount_rejects_value_that_exceeds_its_base(kind, value):
    with pytest.raises(ValueError):
        calculate_discount(Decimal("10.00"), kind, value)


def test_item_and_sale_discounts_accumulate_without_negative_total():
    amounts = calculate_discount_breakdown(
        Decimal("100.00"),
        (Decimal("5.00"), Decimal("10.00")),
        Decimal("20.00"),
    )
    assert amounts.gross == Decimal("100.00")
    assert amounts.total_discount == Decimal("35.00")
    assert amounts.net == Decimal("65.00")
    assert amounts.effective_percent == Decimal("35.00")


def test_combined_discounts_cannot_exceed_gross():
    with pytest.raises(ValueError):
        calculate_discount_breakdown(
            Decimal("10.00"), (Decimal("6.00"),), Decimal("4.01")
        )


def test_seller_limit_requires_admin_and_records_both_actors():
    from stockflow.application.services.sale_service import (
        DiscountApprovalRequired,
        SaleService,
    )
    from stockflow.domain.enums.user_role import UserRole
    from stockflow.infrastructure.repositories.demo_client_repository import (
        DemoClientRepository,
    )
    from stockflow.infrastructure.repositories.demo_product_repository import (
        DemoProductRepository,
    )
    from stockflow.infrastructure.repositories.demo_sale_repository import (
        DemoSaleRepository,
    )
    from stockflow.presentation.demo_accounts import conta_por_papel
    from stockflow.presentation.demo_products import DEMO_PRODUCTS

    products = dict(DEMO_PRODUCTS)
    repository = DemoSaleRepository(products)
    clients = DemoClientRepository()
    service = SaleService(
        repository, clients, DemoProductRepository(products)
    )
    seller = conta_por_papel(UserRole.SELLER).session()
    client = next(item for item in clients.list_all() if item.active)
    items = [{"codigo": "PRD-009", "quantidade": 1}]

    with pytest.raises(DiscountApprovalRequired):
        service.register_sale(
            seller, client.client_id, items, discount="15", discount_type="PERCENTAGE"
        )

    sale = service.register_sale(
        seller,
        client.client_id,
        items,
        discount="15",
        discount_type="PERCENTAGE",
        approval_credentials=("ana.ferreira@example.com", "StockFlow123"),
    )
    assert sale["discount"] == "374.99"
    assert sale["total"] == "2124.91"
    assert sale["discount_applied_by"] == seller.user_id
    assert sale["discount_authorized_by"] == "USR-001"


def test_admin_can_change_seller_discount_limit():
    from stockflow.application.services.sale_service import SaleService
    from stockflow.domain.enums.user_role import UserRole
    from stockflow.infrastructure.repositories.demo_client_repository import (
        DemoClientRepository,
    )
    from stockflow.infrastructure.repositories.demo_product_repository import (
        DemoProductRepository,
    )
    from stockflow.infrastructure.repositories.demo_sale_repository import (
        DemoSaleRepository,
    )
    from stockflow.presentation.demo_accounts import conta_por_papel
    from stockflow.presentation.demo_products import DEMO_PRODUCTS

    products = dict(DEMO_PRODUCTS)
    repository = DemoSaleRepository(products)
    service = SaleService(
        repository, DemoClientRepository(), DemoProductRepository(products)
    )
    admin = conta_por_papel(UserRole.ADMIN).session()

    assert service.set_discount_limits(admin, "5,5")["SELLER"] == Decimal("5.5")
