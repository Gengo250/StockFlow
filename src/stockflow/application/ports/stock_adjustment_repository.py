"""Porta de persistência de ajustes manuais de saldo de estoque."""

from typing import Protocol

from stockflow.application.dto.stock_adjustment_input import StockAdjustmentInput


class StockAdjustmentRepository(Protocol):
    def adjust_confirmed(self, data: StockAdjustmentInput) -> None:
        """Aplica um ajuste confirmado (histórico e saldo no mesmo passo)."""
        ...
