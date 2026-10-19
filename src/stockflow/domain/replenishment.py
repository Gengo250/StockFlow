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
        minimum = to_min(getattr(product, "minimum_stock", None))
        maximum = to_min(getattr(product, "maximum_stock", None))
        status = derive_stock_status(product.stock, minimum)

        if not getattr(product, "active", True) or minimum is None or not is_below_minimum(status):
            continue

        stock = to_int(product.stock)

        # Se o estoque atual atingiu ou ultrapassou o máximo configurado, não sugere reposição
        if maximum is not None and stock >= maximum:
            continue

        # Se houver máximo configurado, o alvo é o máximo; caso contrário, 120% do mínimo
        if maximum is not None:
            target = maximum
            quantity = target - stock
        else:
            target = max(1, (minimum * 6 + 4) // 5)
            quantity = target - stock

        if quantity <= 0:
            continue

        suggestions.append(Replenishment(
            product.code, product.name, stock, minimum, target, quantity, status,
        ))

    return sorted(suggestions, key=lambda item: (SEVERITY[item.status], -item.quantity, item.name.casefold()))