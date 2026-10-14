"""Sugestões para recuperar a faixa normal do estoque, sem gerar compras."""

from dataclasses import dataclass

from stockflow.domain.stock_level import (
    SEVERITY, derive_stock_status, is_below_minimum, to_int, to_min,
)


@dataclass(frozen=True)
class Replenishment:
    code: str
    name: str
    stock: int
    minimum: int
    target: int
    quantity: int
    status: str


def suggest_replenishment(products):
    suggestions = []
    for product in products:
        minimum = to_min(product.minimum_stock)
        status = derive_stock_status(product.stock, minimum)
        if not product.active or minimum is None or not is_below_minimum(status):
            continue
        stock = to_int(product.stock)
        target = max(1, (minimum * 6 + 4) // 5)
        suggestions.append(Replenishment(
            product.code, product.name, stock, minimum, target, target - stock, status,
        ))
    return sorted(suggestions, key=lambda item: (SEVERITY[item.status], -item.quantity, item.name.casefold()))
