from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

from stockflow.application.dto.return_dto import CreateReturnDTO, ReturnItemDTO
from stockflow.application.services.return_service import ReturnService

SALE = "00000000-0000-0000-0000-000000000001"
ITEM = "00000000-0000-0000-0000-000000000002"
RETURN = "00000000-0000-0000-0000-000000000003"
KEY = "abcdefab-0000-0000-0000-000000000004"


class FakeSaleRepository:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def partial_return(self, sale_id, items, reason, idempotency_key):
        self.calls.append((sale_id, items, reason, idempotency_key))
        if self.error:
            raise self.error
        return self.response


def service(repo):
    return ReturnService(repo, SimpleNamespace(role="ADMIN", user_id="admin", company_id="company"))


def dto(items=None, reason="Defeito"):
    return CreateReturnDTO(SALE, [ReturnItemDTO(ITEM, 1)] if items is None else items, reason, KEY)


def result():
    return dict(return_id=RETURN, status="COMPLETED", total_amount=10.5, is_total_return=False)


def test_create_return_success_preserves_complete_contract():
    repo = FakeSaleRepository(result())
    response = service(repo).create_return(dto(reason=" Defeito "))
    assert response == dict(return_id=RETURN, status="COMPLETED",
                           total_amount=Decimal("10.50"), is_total_return=False)
    assert repo.calls == [(SALE, [{"sale_item_id": ITEM, "quantity": 1}], "Defeito", KEY)]


@pytest.mark.parametrize("items,reason", [
    ([], "Defeito"), ([ReturnItemDTO(ITEM, True)], "Defeito"),
    ([ReturnItemDTO(ITEM, 0)], "Defeito"), ([ReturnItemDTO(ITEM, 1)], "   "),
    ([ReturnItemDTO(ITEM, 1), ReturnItemDTO(ITEM.upper(), 1)], "Defeito"),
    ([{"sale_item_id": ITEM, "quantity": 1}], "Defeito"),
])
def test_invalid_request_does_not_write(items, reason):
    repo = FakeSaleRepository(result())
    with pytest.raises(ValueError):
        service(repo).create_return(dto(items, reason))
    assert not repo.calls


@pytest.mark.parametrize("response", [None, {}, [], {"status": "COMPLETED"}])
def test_incomplete_response_fails_without_retry(response):
    repo = FakeSaleRepository(response)
    with pytest.raises(RuntimeError, match="não repita automaticamente"):
        service(repo).create_return(dto())
    assert len(repo.calls) == 1


@pytest.mark.parametrize("field,value", [
    ("is_total_return", "false"), ("status", "PENDING"), ("return_id", "r1"),
    ("total_amount", "NaN"), ("total_amount", "10.001"), ("total_amount", -1),
])
def test_result_fields_are_validated(field, value):
    response = result()
    response[field] = value
    with pytest.raises(RuntimeError):
        service(FakeSaleRepository(response)).create_return(dto())


def test_timeout_is_not_retried_or_masked():
    error = TimeoutError("Resposta perdida")
    repo = FakeSaleRepository(error=error)
    with pytest.raises(TimeoutError) as captured:
        service(repo).create_return(dto())
    assert captured.value is error
    assert len(repo.calls) == 1


@pytest.mark.parametrize("key", [None, "", "key", True, 123])
def test_invalid_idempotency_key_does_not_write(key):
    repo = FakeSaleRepository(result())
    with pytest.raises(ValueError, match="UUID"):
        service(repo).create_return(replace(dto(), idempotency_key=key))
    assert not repo.calls


def test_legacy_dto_without_key_is_rejected_before_write():
    repo = FakeSaleRepository(result())
    with pytest.raises(ValueError, match="UUID"):
        service(repo).create_return(CreateReturnDTO(SALE, [ReturnItemDTO(ITEM, 1)], "Defeito"))
    assert not repo.calls


def test_recovery_after_timeout_preserves_key_and_normalizes_uuid():
    repo = FakeSaleRepository(error=TimeoutError("Resposta perdida"))
    use_case = service(repo)
    request = replace(dto(), idempotency_key=KEY.upper())
    with pytest.raises(TimeoutError):
        use_case.create_return(request)
    repo.error, repo.response = None, result()
    assert use_case.create_return(request)["return_id"] == RETURN
    assert len(repo.calls) == 2
    assert repo.calls[0] == repo.calls[1]
    assert repo.calls[0][-1] == KEY
