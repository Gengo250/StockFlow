"""Dados de um ajuste manual de estoque."""

from dataclasses import dataclass

from stockflow.domain.enums.movement_kind import MovementKind


@dataclass(frozen=True)
class StockAdjustmentInput:
    """Campos que a UI entrega para um ajuste confirmado."""

    product_code: str
    kind: MovementKind
    quantity: int
    justification: str
