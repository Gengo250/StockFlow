"""Testes de interface para múltiplos pagamentos, troco, detalhes e comprovante (US18)."""

from decimal import Decimal

from stockflow.application.services.receipt_renderer import render_receipt_html
from stockflow.domain.sale_receipt import ReceiptCompany, build_sale_receipt
from stockflow.presentation.pages.sale_details import SaleDetailsPage


def _select_first_client_and_product(vendas_page):
    vendas_page.cliente_combo.setCurrentIndex(1)
    vendas_page.produto_combo.setCurrentIndex(1)
    vendas_page.qtd_input.setText("1")
    vendas_page._adicionar_item()


def test_vendas_page_calculates_change_and_registers_split_payments(vendas_page):
    _select_first_client_and_product(vendas_page)
    total = vendas_page._obter_total_venda()
    part1 = (total / 2).quantize(Decimal("0.01"))
    part2_cash = (total - part1) + Decimal("15.00")

    pix_idx = vendas_page.pagamento_combo.findData("PIX")
    vendas_page.pagamento_combo.setCurrentIndex(pix_idx)
    vendas_page.valor_pago_input.setText(f"{part1:.2f}".replace(".", ","))
    vendas_page._adicionar_pagamento()
    assert vendas_page.pagamentos_table.rowCount() == 1
    assert "Falta:" in vendas_page.troco_label.text()

    cash_idx = vendas_page.pagamento_combo.findData("DINHEIRO")
    vendas_page.pagamento_combo.setCurrentIndex(cash_idx)
    vendas_page.valor_pago_input.setText(f"{part2_cash:.2f}".replace(".", ","))
    assert "Troco: R$ 15,00" in vendas_page.troco_label.text()

    vendas_page.save_button.click()
    assert vendas_page.warning_label.text() == ""
    registered = vendas_page.historico_vendas[0]
    assert len(registered["payments"]) == 2
    assert Decimal(registered["change_total"]) == Decimal("15.00")


def test_vendas_page_rejects_underpayment(vendas_page):
    _select_first_client_and_product(vendas_page)
    pix_idx = vendas_page.pagamento_combo.findData("PIX")
    vendas_page.pagamento_combo.setCurrentIndex(pix_idx)
    vendas_page.valor_pago_input.setText("0,01")
    before = len(vendas_page.historico_vendas)

    vendas_page.save_button.click()
    assert len(vendas_page.historico_vendas) == before
    assert "soma dos pagamentos" in vendas_page.warning_label.text().lower()


def test_sale_details_and_receipt_render_multiple_payments_and_change(qapp):
    venda = {
        "id": "VND-9999",
        "data": "26/11/2026 08:20",
        "cliente": "Maria",
        "seller": "João",
        "status": "CONCLUIDA",
        "payment_method": "PIX",
        "total": "100.00",
        "original_total": "100.00",
        "discount": "0.00",
        "change_total": "10.00",
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
                "product_code": "PRD-001",
                "product_name": "Produto A",
                "quantity": 1,
                "unit_price": "100.00",
                "subtotal": "100.00",
                "discount_amount": "0.00",
                "final_subtotal": "100.00",
            }
        ],
    }

    details = SaleDetailsPage()
    details.load_sale(venda)
    text = details.pagamento_label.text()
    assert "Pix" in text
    assert "Dinheiro" in text
    assert "troco" in text.lower()
    assert "10,00" in text

    receipt = build_sale_receipt(venda, ReceiptCompany(name="StockFlow Ltda"))
    html = render_receipt_html(receipt)
    assert "PIX" in html
    assert "DINHEIRO" in html
    assert "Troco" in html
    assert "10,00" in html
