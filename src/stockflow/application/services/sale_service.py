"""Registro comercial; a conclusão baixa o estoque na mesma operação."""

from decimal import Decimal, InvalidOperation
import re

from stockflow.application.dto.sale_item import SaleItemInput, SaleItemValidator
from stockflow.domain.enums.operation_kind import OperationKind
from stockflow.domain.permissions import ensure_can_register_sales
from stockflow.domain.product_status import ensure_product_selectable

_MONEY_PATTERN = re.compile(
    r"(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?|\d+\.\d{1,2}"
)

# Espelha public.payment_method (database/code/tables/06_clients_sales.sql).
# Rótulo que não existe lá seria recusado pelo banco com erro de tipo, que não
# diz ao operador qual é a forma válida.
FORMAS_DE_PAGAMENTO = ("DINHEIRO", "DEBITO", "CREDITO", "PIX", "VALE", "OUTRO")


def parse_total(value) -> Decimal:
    """Converte um preço brasileiro ou decimal para centavos exatos."""
    text = str(value).strip()
    if text.upper().startswith("R$"):
        text = text[2:].strip()
    if not _MONEY_PATTERN.fullmatch(text):
        raise ValueError("Preço do produto inválido.")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("Valor da venda inválido.") from error
    if not amount.is_finite() or amount < 0 or amount >= Decimal("100000000"):
        raise ValueError("Valor da venda inválido.")
    return amount.quantize(Decimal("0.01"))


def calculate_total_from_items(
    items: tuple[SaleItemInput, ...],
    product_codes_to_prices: dict[str, Decimal],
) -> Decimal:
    """Calcula o total exclusivamente com os preços vigentes do catálogo."""
    return sum(
        (
            product_codes_to_prices[item.product_code] * item.quantity
            for item in items
        ),
        start=Decimal("0.00"),
    ).quantize(Decimal("0.01"))


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
        calculado nesta camada é o que a tela mostra. O repositório envia
        apenas código e quantidade; `fn_register_sale` relê os preços de
        `products.sell_price` na mesma transação que valida e baixa o estoque.
        """
        ensure_can_register_sales(session)

        if not itens:
            raise ValueError("Adicione ao menos um item à venda.")
        if payment_method not in FORMAS_DE_PAGAMENTO:
            raise ValueError("Selecione uma forma de pagamento válida.")
        for item in itens:
            self._produto_ativo(item["codigo"])

        normalized_items = tuple(
            SaleItemInput(
                product_code=item["codigo"],
                quantity=parse_quantity(item["quantidade"]),
            )
            for item in itens
        )
        return self.register_multiple(
            session, client_id, normalized_items, payment_method, discount
        )

    def list_sales(self):
        return self.repository.list_all()

    def register_multiple(
        self,
        session,
        client_id,
        items: tuple[SaleItemInput, ...],
        payment_method="DINHEIRO",
        discount="0",
    ) -> dict:
        ensure_can_register_sales(session)

        if not items:
            raise ValueError("Adicione ao menos um item à venda.")
        if payment_method not in FORMAS_DE_PAGAMENTO:
            raise ValueError("Selecione uma forma de pagamento válida.")
        client = self._cliente_ativo(client_id)

        normalized_items = tuple(items)
        item_validator = SaleItemValidator(self.products)
        item_validator.validate(normalized_items)

        products_by_code = {}
        prices_by_code = {}
        for item in normalized_items:
            if item.product_code not in products_by_code:
                product = self.products.get(item.product_code)
                if product is None:
                    raise ValueError(f"Produto {item.product_code} não existe.")
                ensure_product_selectable(
                    product, OperationKind.VENDA, code=item.product_code
                )
                products_by_code[item.product_code] = product
                prices_by_code[item.product_code] = parse_total(product.sale_price)

        bruto = calculate_total_from_items(normalized_items, prices_by_code)
        if bruto >= Decimal("100000000"):
            raise ValueError("Total da venda acima do limite de R$ 99.999.999,99.")
        desconto = parse_total(discount or "0")
        if desconto > bruto:
            raise ValueError(
                "O desconto não pode ser maior que o total dos itens."
            )
        total = bruto - desconto
        # The repository owns the transaction boundary. In particular, stock
        # changes are never performed as a second write after this returns.
        return self.repository.register_multiple(
            client, normalized_items, total, payment_method, desconto
        )
