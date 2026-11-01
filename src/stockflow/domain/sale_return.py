"""Regras puras de devolução; espelho do contrato aprovado das RPCs US20.

O Supabase calcula os valores no banco. O Demo usa estas políticas sobre o
snapshot original, nunca sobre o preço atual do catálogo.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from uuid import UUID

CENT = Decimal("0.01")
MAX_QUANTITY = 2_147_483_647
MAX_AMOUNT = Decimal("9999999999.99")  # numeric(12,2) de returns/return_items
_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def return_identifier(value: str) -> str:
    """UUID no formato aceito pela RPC, normalizado para detectar duplicados."""
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise ValueError("Informe um identificador UUID válido.")
    return str(UUID(value))


def return_quantity(value: int, *, allow_zero: bool = False) -> int:
    if type(value) is not int or not (0 if allow_zero else 1) <= value <= MAX_QUANTITY:
        raise ValueError("Informe uma quantidade inteira dentro do limite permitido.")
    return value


def return_money(value) -> Decimal:
    """Valor monetário não negativo e finito, sem arredondar entrada inválida."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int, float)):
        raise ValueError("Valor monetário inválido.")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not 0 <= amount <= MAX_AMOUNT:
            raise ValueError("Valor monetário inválido.")
        with localcontext() as context:
            context.prec = 50
            rounded = amount.quantize(CENT, rounding=ROUND_HALF_UP)
        if amount != rounded:
            raise ValueError("Valor monetário deve possuir no máximo duas casas decimais.")
        return rounded
    except InvalidOperation as error:
        raise ValueError("Valor monetário inválido.") from error


def validate_return_request(sale_id, items, reason):
    sale_id = return_identifier(sale_id)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Informe o motivo da devolução.")
    if not isinstance(items, (list, tuple)) or not items:
        raise ValueError("Informe ao menos um item para devolução.")
    normalized = []
    seen = set()
    for item_id, quantity in items:
        item_id = return_identifier(item_id)
        if item_id in seen:
            raise ValueError("Item de venda repetido na mesma devolução.")
        seen.add(item_id)
        normalized.append((item_id, return_quantity(quantity)))
    return sale_id, tuple(normalized), reason.strip(" ")


@dataclass(frozen=True)
class OriginalSaleItem:
    sale_item_id: str
    product_code: str
    quantity: int
    unit_price: Decimal
    # Valor monetário do desconto da linha inteira no snapshot original US22.
    discount_amount: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class CalculatedReturnItem:
    sale_item_id: str
    product_code: str
    quantity: int
    unit_price: Decimal
    discount: Decimal
    subtotal: Decimal


def calculate_return_items(
    originals: tuple[OriginalSaleItem, ...],
    discount: Decimal,
    sale_total: Decimal,
    requested: tuple[tuple[str, int], ...],
    returned: dict[str, tuple[int, Decimal]],
) -> tuple[CalculatedReturnItem, ...]:
    """Rateia por UUID e diferenças de acumulados, como fn_return_partial_sale.

    A soma de devoluções 1+1 coincide com a de 2 unidades. A soma dos
    orçamentos líquidos de todos os itens fecha exatamente o total da venda.
    """
    if not originals:
        raise ValueError("Venda sem snapshot de itens para devolução.")
    discount = return_money(Decimal(0) if discount is None else discount)
    sale_total = return_money(sale_total)
    by_id = {}
    for item in originals:
        key = return_identifier(item.sale_item_id)
        if key in by_id:
            raise ValueError("Snapshot da venda contém itens repetidos.")
        return_quantity(item.quantity)
        price = return_money(item.unit_price)
        item_discount = return_money(
            Decimal(0) if item.discount_amount is None else item.discount_amount
        )
        by_id[key] = OriginalSaleItem(key, item.product_code, item.quantity, price, item_discount)
    requests = dict(requested)
    if len(requests) != len(requested) or not requests or requests.keys() - by_id.keys():
        raise ValueError("Item não encontrado na venda ou repetido.")
    with localcontext() as context:
        # Evita dependência da precisão/arredondamento global do chamador.
        context.prec = 50
        gross_total = sum((i.unit_price * i.quantity for i in by_id.values()), Decimal(0))
        item_discount_total = sum((i.discount_amount for i in by_id.values()), Decimal(0))
        if (any(i.discount_amount > i.quantity * i.unit_price for i in by_id.values())
                or discount < item_discount_total or discount > gross_total
                or sale_total != gross_total - discount):
            raise ValueError("Valores originais da venda não conciliam.")
        net_base = gross_total - item_discount_total
        sale_discount = discount - item_discount_total
        cumulative = Decimal(0)
        result = []
        for item_id, item in sorted(by_id.items()):
            base = item.unit_price * item.quantity - item.discount_amount
            previous = cumulative
            cumulative += base
            allocated = Decimal(0) if net_base == 0 else (
                (sale_discount * cumulative / net_base).quantize(CENT, rounding=ROUND_HALF_UP)
                - (sale_discount * previous / net_base).quantize(CENT, rounding=ROUND_HALF_UP)
            )
            line_net = base - allocated
            if item_id not in requests:
                continue
            quantity = return_quantity(requests[item_id])
            old_qty, old_amount = returned.get(item_id, (0, Decimal(0)))
            return_quantity(old_qty, allow_zero=True)
            old_amount = return_money(old_amount)
            if old_qty + quantity > item.quantity:
                raise ValueError("Quantidade excede o disponível para devolução.")
            expected = (line_net * old_qty / item.quantity).quantize(CENT, rounding=ROUND_HALF_UP)
            if old_amount != expected:
                raise ValueError("Histórico de valores devolvidos não concilia.")
            amount = (line_net * (old_qty + quantity) / item.quantity).quantize(
                CENT, rounding=ROUND_HALF_UP
            ) - old_amount
            result.append(CalculatedReturnItem(
                item_id, item.product_code, quantity, item.unit_price,
                return_money(item.unit_price * quantity - amount), return_money(amount),
            ))
        return tuple(result)


def validate_return_stock(stock: int, quantity: int, product_max=None, company_max=None) -> int:
    """O máximo do produto prevalece sobre o da empresa (COALESCE no SQL)."""
    return_quantity(stock, allow_zero=True)
    return_quantity(quantity)
    new_stock = stock + quantity
    if new_stock > MAX_QUANTITY:
        raise ValueError("Saldo resultante acima do limite inteiro permitido.")
    maximum = product_max if product_max is not None else company_max
    if maximum is not None:
        return_quantity(maximum, allow_zero=True)
        if new_stock > maximum:
            raise ValueError("Devolução ultrapassa o estoque máximo permitido.")
    return new_stock
