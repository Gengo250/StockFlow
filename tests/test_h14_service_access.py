"""Recusas por perfil devem ocorrer antes de consultar ou gravar dados."""
from unittest.mock import Mock

import pytest

from stockflow.application.dto.movement_input import MovementInput
from stockflow.application.services.movement_service import MovementService
from stockflow.application.services.sale_service import SaleService
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.presentation.demo_accounts import conta_por_papel


@pytest.mark.parametrize('role', [UserRole.ADMIN, UserRole.STOCK, UserRole.SELLER, None])
@pytest.mark.parametrize('action', ['list_movements', 'register', 'confirm', 'cancel'])
def test_movement_service_access_before_repository(role, action):
    repo = Mock()
    service = MovementService(repo)
    session = conta_por_papel(role).session() if role else None
    args = (() if action == 'list_movements' else
            (MovementInput(product_code='P1', kind=MovementKind.SAIDA, quantity=1),) if action == 'register' else ('M1',))
    if role in (UserRole.ADMIN, UserRole.STOCK):
        getattr(service, action)(session, *args)
        assert len(repo.mock_calls) == 1
    else:
        with pytest.raises(PermissionDeniedError):
            getattr(service, action)(session, *args)
        assert not repo.mock_calls


@pytest.mark.parametrize('role', [UserRole.ADMIN, UserRole.STOCK, UserRole.SELLER, None])
def test_sale_write_access_before_any_repository(role):
    repo, clients, products = Mock(), Mock(), Mock()
    service = SaleService(repo, clients, products)
    session = conta_por_papel(role).session() if role else None
    if role in (UserRole.ADMIN, UserRole.SELLER):
        service.register(session, 'C1', 'P1', '10,00')
        repo.register.assert_called_once()
    else:
        with pytest.raises(PermissionDeniedError):
            service.register(session, 'C1', 'P1', '10,00')
        assert not repo.mock_calls and not clients.mock_calls and not products.mock_calls
