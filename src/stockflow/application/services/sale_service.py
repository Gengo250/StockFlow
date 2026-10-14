"""Regras de registro comercial e totalização de vendas."""

from decimal import Decimal, InvalidOperation
import re

from stockflow.application.dto.sale_item import SaleItemInput, SaleItemValidator
from stockflow.domain.enums.operation_kind import OperationKind
from stockflow.domain.permissions import ensure_can_register_sales
from stockflow.domain.product_status import ensure_product_selectable

_MONEY_PATTERN = re.compile(
    r"(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?|\d+\.\d{1,2}"
)


def parse_total(value) -> Decimal:
    """Converte um preço brasileiro ou decimal para centavos exatos."""
    text = str(value).strip()
    if text.upper().startswith("R$"):
        text = text[2:].strip()
    if not _MONEY_PATTERN.fullmatch(text):
        raise ValueError("Preço do produto inválido.")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("Preço do produto inválido.") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError("Preço do produto inválido.")
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


class SaleService:
    def __init__(self, repository, clients, products):
        self.repository = repository
        self.clients = clients
        self.products = products

    def list_sales(self):
        return self.repository.list_all()

    def register(self, session, client_id, items: tuple[SaleItemInput, ...]) -> dict:
        ensure_can_register_sales(session)

        if not items:
            raise ValueError("A venda deve ter pelo menos um item.")
        client = self.clients.get(client_id)
        if client is None or not client.active:
            raise ValueError("Selecione um cliente ativo válido.")

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

        total = calculate_total_from_items(normalized_items, prices_by_code)
        # The repository owns the transaction boundary. In particular, stock
        # changes are never performed as a second write after this returns.
        return self.repository.register_multiple(client, normalized_items, total)
