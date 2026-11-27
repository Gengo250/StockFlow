"""Testes unitários e de contrato para pagamentos múltiplos e troco (US18)."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.application.services.cash_register_service import payment_totals
from stockflow.application.services.sale_service import SaleService
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.sale_payment import (
    MVP_PAYMENT_METHODS,
    PAYMENT_METHODS,
    SalePaymentInput,
    validate_and_calculate_payments,
)
from stockflow.infrastructure.repositories.demo_client_repository import DemoClientRepository
from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
from stockflow.infrastructure.repositories.demo_product_repository import DemoProductRepository
from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
from stockflow.infrastructure.repositories.supabase_sale_repository import SupabaseSaleRepository
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.demo_products import DEMO_PRODUCTS


def _seller_session():
    return conta_por_papel(UserRole.SELLER).session()


def test_mvp_payment_methods_present_in_allowed_methods():
    for method in MVP_PAYMENT_METHODS:
        assert method in PAYMENT_METHODS


@pytest.mark.parametrize("bad_value", ["0", "0.00", "-10", "-0.01", "abc", ""])
def test_rejects_non_positive_or_invalid_payment_values(bad_value):
    with pytest.raises(ValueError):
        validate_and_calculate_payments(
            [SalePaymentInput("PIX", bad_value)], Decimal("50.00")
        )


def test_rejects_empty_payments_for_positive_sale():
    with pytest.raises(ValueError, match="pelo menos uma forma"):
        validate_and_calculate_payments([], Decimal("50.00"))


def test_rejects_sum_not_matching_sale_total():
    with pytest.raises(ValueError, match="soma dos pagamentos"):
        validate_and_calculate_payments(
            [SalePaymentInput("PIX", "30.00"), SalePaymentInput("DEBITO", "10.00")],
            Decimal("50.00"),
        )


def test_rejects_change_for_non_cash_payment():
    with pytest.raises(ValueError, match="exceder"):
        validate_and_calculate_payments(
            [SalePaymentInput("PIX", "60.00")], Decimal("50.00")
        )


def test_calculates_change_for_cash_payment():
    breakdown = validate_and_calculate_payments(
        [SalePaymentInput("DINHEIRO", "100.00")], Decimal("65.50")
    )
    assert breakdown.total_applied == Decimal("65.50")
    assert breakdown.total_received == Decimal("100.00")
    assert breakdown.total_change == Decimal("34.50")
    assert len(breakdown.payments) == 1
    assert breakdown.payments[0].amount == Decimal("65.50")
    assert breakdown.payments[0].received_amount == Decimal("100.00")
    assert breakdown.payments[0].change_amount == Decimal("34.50")


def test_split_payment_with_cash_change():
    breakdown = validate_and_calculate_payments(
        [
            SalePaymentInput("PIX", "40.00"),
            SalePaymentInput("DINHEIRO", "50.00"),
        ],
        Decimal("75.00"),
    )
    assert breakdown.total_applied == Decimal("75.00")
    assert breakdown.total_received == Decimal("90.00")
    assert breakdown.total_change == Decimal("15.00")
    assert breakdown.payments[0].amount == Decimal("40.00")
    assert breakdown.payments[0].change_amount == Decimal("0.00")
    assert breakdown.payments[1].amount == Decimal("35.00")
    assert breakdown.payments[1].received_amount == Decimal("50.00")
    assert breakdown.payments[1].change_amount == Decimal("15.00")


def test_demo_sale_service_persists_split_payments_and_deducts_stock_atomically():
    products = {k: v for k, v in DEMO_PRODUCTS.items()}
    code = next(iter(products))
    initial_stock = int(str(products[code].stock).split()[0])
    movements = DemoMovementRepository(products)
    sales_repo = DemoSaleRepository(products, movements, session=_seller_session())
    clients_repo = DemoClientRepository()
    client_id = next(c for c in clients_repo.list_all() if c.active).client_id
    service = SaleService(sales_repo, clients_repo, DemoProductRepository(products))

    unit_price = Decimal(
        str(products[code].sale_price).replace("R$", "").replace(".", "").replace(",", ".").strip()
    )
    total = unit_price * 2
    half = (total / 2).quantize(Decimal("0.01"))
    rest = total - half + Decimal("10.00")

    sale = service.register_sale(
        _seller_session(),
        client_id,
        [{"codigo": code, "quantidade": 2}],
        payments=[
            SalePaymentInput("DEBITO", half),
            SalePaymentInput("DINHEIRO", rest),
        ],
    )
    assert int(str(products[code].stock).split()[0]) == initial_stock - 2
    assert len(sale["payments"]) == 2
    assert sale["payments"][0]["payment_method"] == "DEBITO"
    assert Decimal(sale["payments"][0]["amount"]) == half
    assert sale["payments"][1]["payment_method"] == "DINHEIRO"
    assert Decimal(sale["payments"][1]["change_amount"]) == Decimal("10.00")
    assert Decimal(sale["change_total"]) == Decimal("10.00")

    # Fechamento de caixa soma os valores aplicados por forma de pagamento
    totals = payment_totals([sale])
    assert totals["DEBITO"] == half
    assert totals["DINHEIRO"] == total - half


def test_demo_sale_rollback_on_payment_failure_preserves_stock():
    products = {k: v for k, v in DEMO_PRODUCTS.items()}
    code = next(iter(products))
    initial_stock = products[code].stock
    movements = DemoMovementRepository(products)
    sales_repo = DemoSaleRepository(products, movements, session=_seller_session())
    clients_repo = DemoClientRepository()
    client_id = next(c for c in clients_repo.list_all() if c.active).client_id
    service = SaleService(sales_repo, clients_repo, DemoProductRepository(products))
    before_sales = len(sales_repo.list_all())

    with pytest.raises(ValueError):
        service.register_sale(
            _seller_session(),
            client_id,
            [{"codigo": code, "quantidade": 1}],
            payments=[SalePaymentInput("PIX", "0.01")],
        )
    assert products[code].stock == initial_stock
    assert len(sales_repo.list_all()) == before_sales


def test_supabase_sale_repository_sends_p_payments_when_provided():
    calls = []

    class FakeExec:
        def __init__(self, data):
            self.data = data

    class FakeAPI:
        def rpc(self, name, payload):
            calls.append((name, payload))
            return SimpleNamespace(
                execute=lambda: FakeExec({
                    "id": "sale-1",
                    "cliente": "Cliente",
                    "total": "100.00",
                    "original_total": "100.00",
                    "discount": "0.00",
                    "payment_method": "PIX",
                    "change_total": "10.00",
                    "created_on": "2026-11-26T10:00:00Z",
                    "payments": [
                        {
                            "payment_method": "PIX",
                            "amount": "60.00",
                            "received_amount": "60.00",
                            "change_amount": "0.00",
                        },
                        {
                            "payment_method": "DINHEIRO",
                            "amount": "40.00",
                            "received_amount": "50.00",
                            "change_amount": "10.00",
                        },
                    ],
                    "items": [
                        {
                            "product_code": "P1",
                            "product_name": "Produto",
                            "quantity": 1,
                            "unit_price": "100.00",
                            "subtotal": "100.00",
                        }
                    ],
                })
            )

    repo = SupabaseSaleRepository(FakeAPI(), "company-1")
    breakdown = validate_and_calculate_payments(
        [SalePaymentInput("PIX", "60.00"), SalePaymentInput("DINHEIRO", "50.00")],
        Decimal("100.00"),
    )
    row = repo.register_multiple(
        SimpleNamespace(client_id="client-1"),
        (SaleItemInput("P1", 1),),
        Decimal("100.00"),
        "PIX",
        payments=breakdown.payments,
    )
    assert calls[0][0] == "fn_register_sale_with_discounts"
    assert len(calls[0][1]["p_payments"]) == 2
    assert row["change_total"] == "10.00"
    assert len(row["payments"]) == 2
