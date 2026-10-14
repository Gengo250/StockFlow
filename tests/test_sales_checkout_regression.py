"""Regressões reproduzidas pela auditoria de vendas de 13/10/2026."""

from decimal import Decimal
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QAbstractItemView

from stockflow.application.services.sale_service import parse_total


def select_sale(page, quantity="2"):
    assert page.selecionar_cliente_externo("Carlos Mendes")
    assert page.selecionar_produto("PRD-009")
    page.qtd_input.setText(quantity)


def test_direct_checkout_uses_quantity_and_catalog_price(vendas_page):
    select_sale(vendas_page)
    vendas_page.save_button.click()
    sale = vendas_page.historico_vendas[0]
    assert sale["total"] == "4999.80"
    assert sale["produto"].startswith("2x ")


def test_price_is_read_only_and_filled_by_product_selection(vendas_page):
    select_sale(vendas_page)
    assert vendas_page.val_input.isReadOnly()
    assert vendas_page.val_input.text() == "R$ 2.499,90"


def test_discount_updates_preview_without_calling_a_private_refresh(vendas_page):
    select_sale(vendas_page, "1")
    vendas_page.add_button.click()
    vendas_page.desconto_input.setText("499,90")
    assert vendas_page.total_label.text() == "Total: R$ 2.000,00"


def test_checkout_does_not_silently_drop_the_selected_product(vendas_page):
    select_sale(vendas_page, "1")
    vendas_page.add_button.click()
    assert vendas_page.selecionar_produto("PRD-008")
    vendas_page.qtd_input.setText("2")
    vendas_page.save_button.click()
    assert vendas_page.historico_vendas[0]["total"] == "3419.70"


def test_tables_do_not_offer_edits_that_are_never_saved(vendas_page):
    for table in (vendas_page.table, vendas_page.itens_table):
        assert table.editTriggers() == QAbstractItemView.NoEditTriggers


def test_demo_checkout_changes_stock_and_rejects_overdraw(vendas_page):
    select_sale(vendas_page, "1")
    before = int(vendas_page.products["PRD-009"].stock)
    vendas_page.save_button.click()
    assert int(vendas_page.products["PRD-009"].stock) == before - 1
    select_sale(vendas_page, str(before + 1))
    sales_before = len(vendas_page.historico_vendas)
    vendas_page.save_button.click()
    assert len(vendas_page.historico_vendas) == sales_before
    assert "insuficiente" in vendas_page.warning_label.text().lower()


def test_busy_checkout_cannot_be_submitted_twice(vendas_page):
    queued = []
    vendas_page.execute = lambda *args: queued.append(args)
    select_sale(vendas_page, "1")
    vendas_page.save_button.click()
    vendas_page._registrar_venda()
    assert len(queued) == 1
    assert not vendas_page.save_button.isEnabled()
    operation, success, failure = queued.pop()
    success(operation())
    assert vendas_page.save_button.isEnabled()


@pytest.mark.parametrize("text,expected", [("1.000", "1000.00"), ("1.000,00", "1000.00")])
def test_brazilian_grouped_amount_is_not_divided_by_a_thousand(text, expected):
    assert parse_total(text) == Decimal(expected)


def test_sale_amount_respects_numeric_10_2_limit():
    with pytest.raises(ValueError):
        parse_total("100000000.00")


def test_cart_preview_refreshes_when_catalog_price_changes(vendas_page):
    select_sale(vendas_page, "2")
    vendas_page.add_button.click()
    product = vendas_page.products["PRD-009"]
    vendas_page.products[product.code] = replace(product, sale_price="R$ 2.000,00")
    vendas_page.reload_products()
    assert vendas_page.total_label.text() == "Total: R$ 4.000,00"
    assert vendas_page.itens_table.item(0, 2).text() == "R$ 2.000,00"


def test_failed_checkout_keeps_cart_and_can_be_retried(vendas_page):
    select_sale(vendas_page, "1")
    operation = vendas_page.service.register_sale
    vendas_page.service.register_sale = lambda *a: (_ for _ in ()).throw(ValueError("Falha de conexão"))
    vendas_page.save_button.click()
    assert "conexão" in vendas_page.warning_label.text()
    assert len(vendas_page.itens) == 1
    assert vendas_page.save_button.isEnabled()
    vendas_page.service.register_sale = operation
    before = len(vendas_page.historico_vendas)
    vendas_page.save_button.click()
    assert len(vendas_page.historico_vendas) == before + 1
    assert vendas_page.itens == []


class CheckoutAPI:
    def __init__(self):
        self.calls = []
        self.receipt = {
            "id": "sale-1", "client_name": "Cliente persistido", "total": "37.50",
            "created_on": "2026-10-14T12:00:00+00:00", "status": "CONCLUIDA",
            "payment_method": "PIX", "discount": "2.50",
            "sale_items": [{"product_code": "PRD-009", "product_name": "Nome persistido",
                            "quantity": 2, "unit_price": "20.00", "subtotal": "40.00"}],
        }

    def table(self, name):
        self.calls.append(("table", name))
        self.data = [self.receipt] if name == "sales" else [{"id": "product-1", "barcode": "PRD-009"}]
        return self

    def select(self, columns):
        self.calls.append(("select", columns))
        return self

    def eq(self, *args):
        return self

    def in_(self, *args):
        return self

    def order(self, *args, **kwargs):
        return self

    def rpc(self, name, args):
        self.calls.append(("rpc", name, args))
        self.data = self.receipt
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


def test_supabase_checkout_uses_saved_receipt_without_second_read(vendas_page):
    from stockflow.infrastructure.repositories.supabase_sale_repository import SupabaseSaleRepository
    api = CheckoutAPI()
    repository = SupabaseSaleRepository(api, "company-1")
    row = repository.register_items(SimpleNamespace(client_id="client-1"),
        [{"product": vendas_page.products["PRD-009"], "quantity": 2}], "PIX", Decimal("2.50"), Decimal("999"))
    assert row["total"] == "37.50"
    assert row["cliente"] == "Cliente persistido"
    assert row["items"] == api.receipt["sale_items"]
    assert api.calls[-1][0:2] == ("rpc", "fn_checkout_sale")
    assert api.calls[-1][2]["p_items"] == [{"product_id": "product-1", "quantity": 2}]


def test_reloaded_history_keeps_payment_and_item_details():
    from stockflow.infrastructure.repositories.supabase_sale_repository import SupabaseSaleRepository
    api = CheckoutAPI()
    row = SupabaseSaleRepository(api, "company-1").list_all()[0]
    assert row["items"] == api.receipt["sale_items"]
    assert row["payment_method"] == "PIX"
    assert row["discount"] == "2.50"
    assert "unit_price" in next(c[1] for c in api.calls if c[0] == "select")
