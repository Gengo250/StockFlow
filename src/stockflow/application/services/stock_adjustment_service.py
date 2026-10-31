"""Casos de uso de ajuste manual de estoque."""

from stockflow.application.dto.stock_adjustment_input import StockAdjustmentInput
from stockflow.application.ports.stock_adjustment_repository import (
    StockAdjustmentRepository,
)
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.permissions import ensure_can_move_stock


class StockAdjustmentService:
    def __init__(
        self,
        repository: StockAdjustmentRepository,
        product_repository=None,
    ):
        self._repository = repository
        self._product_repository = product_repository

    def adjust_confirmed(self, session, data: StockAdjustmentInput) -> None:
        ensure_can_move_stock(session, action="ajustar saldo do estoque")

        if not (data.product_code or "").strip():
            raise ValueError("Selecione o produto do ajuste.")

        if self._product_repository is not None:
            product = self._product_repository.get(data.product_code)
            if product is None or not getattr(product, "active", False):
                raise ValueError("Selecione um produto ativo.")

        quantidade = _para_inteiro(data.quantity)
        if quantidade <= 0:
            raise ValueError("A quantidade do ajuste deve ser maior que zero.")

        # Valida valor do enum antes de chamar o banco.
        kind = MovementKind.from_value(data.kind)

        justificativa = str(getattr(data, "justification", "") or "").strip()
        if not justificativa:
            raise ValueError("Justificativa é obrigatória para ajustes de estoque.")

        self._repository.adjust_confirmed(
            StockAdjustmentInput(
                product_code=str(data.product_code).strip(),
                kind=kind,
                quantity=quantidade,
                justification=justificativa,
            )
        )


def _para_inteiro(valor) -> int:
    try:
        return int(str(valor).strip() or 0)
    except (ValueError, TypeError):
        return 0
