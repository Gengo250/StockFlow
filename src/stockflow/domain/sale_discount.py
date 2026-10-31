"""Regras monetárias de descontos em itens e vendas."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


class DiscountKind(StrEnum):
    FIXED = "FIXED"
    PERCENTAGE = "PERCENTAGE"


@dataclass(frozen=True)
class DiscountBreakdown:
    gross: Decimal
    item_discount: Decimal
    sale_discount: Decimal
    total_discount: Decimal
    net: Decimal
    effective_percent: Decimal


def calculate_discount(base: Decimal, kind: DiscountKind | str, value: Decimal) -> Decimal:
    """Calcula desconto em centavos e recusa bases/valores fora do domínio."""
    try:
        discount_kind = DiscountKind(kind)
        amount = Decimal(value)
        subtotal = Decimal(base)
    except (ValueError, TypeError, ArithmeticError) as error:
        raise ValueError("Tipo ou valor de desconto inválido.") from error

    if not amount.is_finite() or not subtotal.is_finite():
        raise ValueError("Tipo ou valor de desconto inválido.")
    if subtotal < 0 or amount < 0:
        raise ValueError("O desconto e sua base devem ser não negativos.")
    if discount_kind is DiscountKind.PERCENTAGE:
        if amount > HUNDRED:
            raise ValueError("O desconto percentual deve estar entre 0% e 100%.")
        discount = (subtotal * amount / HUNDRED).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
    else:
        discount = amount.quantize(CENT, rounding=ROUND_HALF_UP)

    if discount > subtotal:
        raise ValueError("O desconto não pode ser maior que a base.")
    return discount


def calculate_discount_breakdown(
    gross: Decimal,
    item_discounts: tuple[Decimal, ...],
    sale_discount: Decimal,
) -> DiscountBreakdown:
    """Combina descontos dos itens e do total, sem permitir total negativo."""
    gross_total = Decimal(gross).quantize(CENT, rounding=ROUND_HALF_UP)
    item_total = sum(
        (Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP) for value in item_discounts),
        start=ZERO,
    )
    sale_total = Decimal(sale_discount).quantize(CENT, rounding=ROUND_HALF_UP)
    if not all(value.is_finite() for value in (gross_total, item_total, sale_total)):
        raise ValueError("O total ou desconto da venda é inválido.")
    if gross_total < 0 or item_total < 0 or sale_total < 0:
        raise ValueError("O total ou desconto da venda é inválido.")
    if item_total + sale_total > gross_total:
        raise ValueError("O desconto não pode ser maior que o total dos itens.")
    discount_total = item_total + sale_total
    effective_percent = (
        discount_total * HUNDRED / gross_total if gross_total else ZERO
    )
    return DiscountBreakdown(
        gross=gross_total,
        item_discount=item_total,
        sale_discount=sale_total,
        total_discount=discount_total,
        net=gross_total - discount_total,
        effective_percent=effective_percent,
    )
