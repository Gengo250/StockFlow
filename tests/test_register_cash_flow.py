from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4
import pytest
from stockflow.application.dto.register_input import (
    OpenRegisterInput,
    CloseRegisterInput,
)
from stockflow.application.services.register_service import RegisterService
from stockflow.infrastructure.repositories.supabase_register_repository import (
    SupabaseRegisterRepository,
)


@pytest.fixture
def mock_supabase():
    return Mock()


def test_open_register_success(mock_supabase):
    fake_log_id = str(uuid4())
    mock_supabase.rpc.return_value.execute.return_value.data = fake_log_id

    repo = SupabaseRegisterRepository(mock_supabase)
    service = RegisterService(repo)

    input_dto = OpenRegisterInput(
        company_id=uuid4(),
        register_id=uuid4(),
        operator_id=uuid4(),
        initial_balance=Decimal("150.00"),
    )

    res = service.open_register(input_dto)
    assert str(res) == fake_log_id
    mock_supabase.rpc.assert_called_with(
        "fn_open_register_session",
        {
            "p_company_id": str(input_dto.company_id),
            "p_register_id": str(input_dto.register_id),
            "p_operator_id": str(input_dto.operator_id),
            "p_session_id": None,
            "p_initial_balance": 150.0,
        },
    )


def test_open_register_rejects_negative_balance():
    with pytest.raises(ValueError):
        OpenRegisterInput(
            company_id=uuid4(),
            register_id=uuid4(),
            operator_id=uuid4(),
            initial_balance=Decimal("-10.00"),
        )


def test_close_register_success(mock_supabase):
    fake_res = {
        "status": "CLOSED",
        "difference": 0.0,
        "total_expected": 200.0,
        "total_declared": 200.0,
    }
    mock_supabase.rpc.return_value.execute.return_value.data = fake_res

    repo = SupabaseRegisterRepository(mock_supabase)
    service = RegisterService(repo)

    input_dto = CloseRegisterInput(
        register_log_id=uuid4(), declared_dinheiro=Decimal("200.00")
    )

    res = service.close_register(input_dto)
    assert res["status"] == "CLOSED"
    assert res["difference"] == 0.0


def test_close_register_propagates_database_error(mock_supabase):
    mock_supabase.rpc.return_value.execute.side_effect = RuntimeError(
        "Divergência de valores detectada. É obrigatório informar uma justificativa."
    )

    repo = SupabaseRegisterRepository(mock_supabase)
    service = RegisterService(repo)

    input_dto = CloseRegisterInput(
        register_log_id=uuid4(), declared_dinheiro=Decimal("50.00"), justification=None
    )

    with pytest.raises(RuntimeError, match="justificativa"):
        service.close_register(input_dto)
