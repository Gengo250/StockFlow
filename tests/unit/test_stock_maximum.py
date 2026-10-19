"""Contrato síncrono do ajuste: sessão autorizada e justificativa preservada."""
from unittest.mock import Mock

import pytest

from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.application.ports.movement_repository import MovementRepository
from stockflow.application.services.movement_service import MovementService
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel


def test_adjust_stock_success():
    repo = Mock(spec=MovementRepository)
    repo.adjust.return_value = "movement-id"
    data = AdjustmentInput("P1", 10, 20, AdjustmentReason.OUTRO, "Inventário mensal")

    result = MovementService(repo).adjust(conta_por_papel(UserRole.STOCK).session(), data)

    assert result == "movement-id"
    repo.adjust.assert_called_once_with(data)


def test_adjust_stock_missing_justification():
    repo = Mock(spec=MovementRepository)
    data = AdjustmentInput("P1", 10, 20, AdjustmentReason.OUTRO, "   ")

    with pytest.raises(ValueError, match="justificativa escrita"):
        MovementService(repo).adjust(conta_por_papel(UserRole.STOCK).session(), data)

    repo.adjust.assert_not_called()
