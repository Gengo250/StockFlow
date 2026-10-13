"""Regras de registro comercial; movimentação de estoque é um fluxo separado."""

from decimal import Decimal, InvalidOperation
import re

from stockflow.domain.permissions import ensure_can_register_sales

# Espelha public.payment_method (database/code/tables/06_clients_sales.sql).
# Rótulo que não existe lá seria recusado pelo banco com erro de tipo, que não
# diz ao operador qual é a forma válida.
FORMAS_DE_PAGAMENTO = ("DINHEIRO", "DEBITO", "CREDITO", "PIX", "VALE", "OUTRO")


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


def parse_price(value) -> Decimal:
    """Preço do catálogo ("R$ 2.499,90") como Decimal."""
    return parse_total(str(value).replace("R$", "").strip())


def parse_quantity(value) -> int:
    text = str(value).strip()
    if not re.fullmatch(r"\d+", text) or int(text) <= 0:
        raise ValueError("Informe uma quantidade inteira maior que zero.")
    quantidade = int(text)
    if quantidade > 1_000_000:
        raise ValueError("Quantidade acima do limite por item.")
    return quantidade


class SaleService:
    def __init__(self, repository, clients, products):
        self.repository, self.clients, self.products = repository, clients, products

    def _cliente_ativo(self, client_id):
        client = self.clients.get(client_id)
        if client is None or not client.active:
            raise ValueError("Selecione um cliente ativo válido.")
        return client

    def _produto_ativo(self, product_code):
        product = self.products.get(product_code)
        if product is None or not product.active:
            raise ValueError("Selecione um produto ativo válido.")
        return product

    def register(self, session, client_id, product_code, value):
        ensure_can_register_sales(session)
        total = parse_total(value)
        client = self._cliente_ativo(client_id)
        product = self._produto_ativo(product_code)
        return self.repository.register(client, product, total)

    def register_sale(self, session, client_id, itens,
                      payment_method="DINHEIRO", discount="0"):
        """Venda com vários itens, forma de pagamento e desconto (US10).

        `itens` são pares código/quantidade. O preço NÃO vem daqui: o total
        calculado nesta camada é o que a tela mostra, e quem grava o valor
        cobrado é `fn_create_complete_sale`, lendo `products.sell_price`. Se
        os dois divergirem, o do banco é que vale.
        """
        ensure_can_register_sales(session)

        if not itens:
            raise ValueError("Adicione ao menos um item à venda.")
        if payment_method not in FORMAS_DE_PAGAMENTO:
            raise ValueError("Selecione uma forma de pagamento válida.")

        client = self._cliente_ativo(client_id)
        desconto = parse_total(discount or "0")

        resolvidos, bruto = [], Decimal("0")
        for item in itens:
            product = self._produto_ativo(item["codigo"])
            quantidade = parse_quantity(item["quantidade"])
            resolvidos.append({"product": product, "quantity": quantidade})
            bruto += parse_price(product.sale_price) * quantidade

        if desconto > bruto:
            raise ValueError(
                "O desconto não pode ser maior que o total dos itens."
            )

        return self.repository.register_items(
            client, resolvidos, payment_method, desconto, bruto - desconto
        )

    def list_sales(self):
        return self.repository.list_all()
