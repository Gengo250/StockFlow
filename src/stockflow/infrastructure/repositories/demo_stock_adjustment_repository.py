"""Implementação demo de ajuste manual de estoque.

No modo demonstração não existe trigger; o equivalente do banco é
registrar uma movimentação CONFIRMADA, porque isso mantém o histórico e
altera o saldo no mesmo fluxo.
"""

from stockflow.application.dto.movement_input import MovementInput
from stockflow.application.dto.stock_adjustment_input import (
    StockAdjustmentInput,
)
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.infrastructure.repositories.demo_movement_repository import (
    DemoMovementRepository,
)


class DemoStockAdjustmentRepository:
    def __init__(self, movement_repository: DemoMovementRepository):
        self._movements = movement_repository

    def adjust_confirmed(self, data: StockAdjustmentInput) -> None:
        # Reaproveita a mesma entidade de histórico e saldo do modo demo.
        self._movements.register(
            MovementInput(
                product_code=data.product_code,
                kind=MovementKind.from_value(data.kind),
                quantity=int(data.quantity),
                note=data.justification,
                confirm=True,
            )
        )
