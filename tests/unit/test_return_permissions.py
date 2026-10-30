from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from stockflow.application.dto.return_dto import CreateReturnDTO, ReturnItemDTO
from stockflow.application.dto.return_eligibility import ReturnEligibilityDTO
from stockflow.application.services.return_service import ReturnEligibilityService, ReturnService
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.permissions import can_return_sales, ensure_can_return_sales

SALE = "00000000-0000-0000-0000-000000000001"
ITEM = "00000000-0000-0000-0000-000000000002"


@pytest.mark.parametrize("role,expected", [("ADMIN", True), ("STOCK", False),
                                          ("SELLER", False), (None, False), ("GERENTE", False)])
def test_permission_matches_admin_only_rpc(role, expected):
    assert can_return_sales(role) is expected


@pytest.mark.parametrize("session", [
    None, "ADMIN", SimpleNamespace(role="ADMIN"),
    SimpleNamespace(role="ADMIN", user_id="", company_id="company"),
    SimpleNamespace(role="ADMIN", user_id="admin", company_id=None),
    SimpleNamespace(role="SELLER", user_id="seller", company_id="company"),
    SimpleNamespace(role="STOCK", user_id="stock", company_id="company"),
])
def test_missing_context_or_permission_never_calls_adapter(session):
    repo = Mock()
    with pytest.raises(PermissionDeniedError):
        ReturnEligibilityService(repo, session).get_returnable(ReturnEligibilityDTO(SALE))
    with pytest.raises(PermissionDeniedError):
        ReturnService(repo, session).create_return(CreateReturnDTO(SALE, [ReturnItemDTO(ITEM, 1)], "Defeito"))
    assert repo.mock_calls == []


def test_admin_session_is_allowed():
    ensure_can_return_sales(SimpleNamespace(role="ADMIN", user_id="admin", company_id="company"))
