"""Regras de registro comercial; movimentação de estoque é um fluxo separado."""

from decimal import Decimal, InvalidOperation
import re

from stockflow.domain.permissions import ensure_can_register_sales


def parse_total(value) -> Decimal:
    text = str(value).strip()
    # Accept either a decimal dot or Brazilian grouping/decimal notation.
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?|\d+\.\d{1,2}", text):
        raise ValueError("Informe um valor válido, com até duas casas decimais.")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        total = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("Valor da venda inválido.") from error
    if not total.is_finite() or total < 0 or total >= Decimal("10000000000"):
        raise ValueError("Valor da venda inválido.")
    return total.quantize(Decimal("0.01"))


class SaleService:
    def __init__(self, repository, clients, products):
        self.repository, self.clients, self.products = repository, clients, products

    def register(self, session, client_id, product_code, value):
        ensure_can_register_sales(session)
        total = parse_total(value)
        client = self.clients.get(client_id)
        if client is None or not client.active:
            raise ValueError("Selecione um cliente ativo válido.")
        product = self.products.get(product_code)
        if product is None or not product.active:
            raise ValueError("Selecione um produto ativo válido.")
        return self.repository.register(client, product, total)

    def list_sales(self):
        return self.repository.list_all()
