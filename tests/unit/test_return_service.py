from types import SimpleNamespace

import pytest

from stockflow.application.dto.return_eligibility import ReturnEligibilityDTO
from stockflow.application.services.return_service import ReturnEligibilityService

SALE = "00000000-0000-0000-0000-000000000001"
ITEM = "00000000-0000-0000-0000-000000000002"
PRODUCT = "00000000-0000-0000-0000-000000000003"


class FakeSaleRepository:
    def __init__(self, items=None, error=None):
        self.items, self.error, self.calls = items, error, []

    def get_returnable_items(self, sale_id):
        self.calls.append(sale_id)
        if self.error:
            raise self.error
        return self.items


def service(repo):
    return ReturnEligibilityService(
        repo, SimpleNamespace(role="ADMIN", user_id="admin", company_id="company")
    )


def item():
    return dict(sale_item_id=ITEM, product_id=PRODUCT, product_name="Caneta",
                quantity_sold=10, quantity_returned=3, max_returnable=7)


def test_get_returnable_success():
    repo = FakeSaleRepository([item()])
    result = service(repo).get_returnable(ReturnEligibilityDTO(SALE))
    assert result[0].sale_item_id == ITEM
    assert result[0].max_returnable == 7
    assert repo.calls == [SALE]


def test_empty_list_is_valid():
    assert service(FakeSaleRepository([])).get_returnable(ReturnEligibilityDTO(SALE)) == []


def test_deleted_product_preserves_original_name():
    row = item()
    row["product_id"] = None
    result = service(FakeSaleRepository([row])).get_returnable(ReturnEligibilityDTO(SALE))
    assert result[0].product_id is None
    assert result[0].product_name == "Caneta"


@pytest.mark.parametrize("response", [None, {}, False, [None], [item(), item()]])
def test_invalid_response_is_not_empty_success(response):
    with pytest.raises(RuntimeError, match="Resposta"):
        service(FakeSaleRepository(response)).get_returnable(ReturnEligibilityDTO(SALE))


@pytest.mark.parametrize("field,value", [
    ("quantity_sold", True), ("quantity_returned", -1), ("max_returnable", 8),
    ("product_id", "invalid"), ("sale_item_id", "invalid"), ("product_name", None),
])
def test_invalid_row_is_rejected(field, value):
    row = item()
    row[field] = value
    with pytest.raises(RuntimeError):
        service(FakeSaleRepository([row])).get_returnable(ReturnEligibilityDTO(SALE))


@pytest.mark.parametrize("error", [ValueError("Venda não encontrada"), TimeoutError("rede")])
def test_adapter_error_is_preserved(error):
    repo = FakeSaleRepository(error=error)
    with pytest.raises(type(error)) as captured:
        service(repo).get_returnable(ReturnEligibilityDTO(SALE))
    assert captured.value is error


def test_invalid_identifier_does_not_call_repository():
    repo = FakeSaleRepository([])
    with pytest.raises(ValueError):
        service(repo).get_returnable(ReturnEligibilityDTO("invalid"))
    assert repo.calls == []
