
import pytest
from unittest.mock import AsyncMock
import uuid
from uuid import uuid4
from stockflow.application.services.movement_service import MovementService
from stockflow.application.dto.movement_input import MovementInput

@pytest.fixture
def repo_mock():
    # Simula o Repositório do Supabase
    repo = AsyncMock()
    repo.adjust.return_value = str(uuid.uuid4()) # Simula retorno de ID do log
    return repo

@pytest.fixture
def service(repo_mock):
    return MovementService(repository=repo_mock)

@pytest.mark.asyncio
async def test_adjust_stock_success(service, repo_mock):
    """Valida que o Service chama o repositório corretamente quando os dados são válidos."""
    data = MovementInput(
        product_id=uuid4(),
        company_id=uuid4(),
        quantity=10,
        movement_kind='ENTRADA',
        justification="Ajuste de inventário mensal",
        user_id=uuid4()
    )

    result = await service.adjust(None, data) # session=None para teste unitário

    assert result is not None
    repo_mock.adjust.assert_awaited_once_with(data)

@pytest.mark.asyncio
async def test_adjust_stock_missing_justification(service, repo_mock):
    """Valida que o Service bloqueia ajustes sem justificativa."""
    data = MovementInput(
        product_id=uuid4(),
        company_id=uuid4(),
        quantity=10,
        movement_kind='ENTRADA',
        justification="", # VAZIO!
        user_id=uuid4()
    )

    with pytest.raises(ValueError) as exc:
        await service.adjust(None, data)

    assert "Justificativa é obrigatória" in str(exc.value)
    # Garante que o repositório NÃO foi chamado
    repo_mock.adjust.assert_not_awaited()
