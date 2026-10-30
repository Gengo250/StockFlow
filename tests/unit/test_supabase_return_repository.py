from decimal import Decimal
from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.supabase_sale_repository import SupabaseSaleRepository

SALE = "00000000-0000-0000-0000-000000000001"
ITEM = "00000000-0000-0000-0000-000000000002"
RETURN = "00000000-0000-0000-0000-000000000003"
KEY = "abcdefab-0000-0000-0000-000000000004"
PAYLOAD = [{"sale_item_id": ITEM, "quantity": 1}]


class API:
    def __init__(self, data=None, error=None):
        self.data, self.error, self.calls = data, error, []

    def rpc(self, name, args):
        self.calls.append((name, args))
        return self

    def execute(self):
        if self.error:
            raise self.error
        return SimpleNamespace(data=self.data)

    def table(self, *args):
        raise AssertionError("A devolução deve usar apenas a RPC, sem escritas/leituras extras.")


def test_register_uses_one_rpc_and_complete_result(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("PHP não deve ser executado nesta etapa.")
    monkeypatch.setattr(
        "stockflow.infrastructure.repositories.supabase_sale_repository.NFeClient.emitir_nota", forbidden
    )
    api = API(dict(return_id=RETURN, status="COMPLETED", total_amount="10.50", is_total_return=True))
    result = SupabaseSaleRepository(api, "company").partial_return(SALE, PAYLOAD, " Defeito ", KEY)
    assert api.calls == [("fn_return_partial_sale", {
        "p_sale_id": SALE, "p_items": PAYLOAD, "p_reason": "Defeito",
        "p_idempotency_key": KEY,
    })]
    assert result["total_amount"] == Decimal("10.50")
    assert result["is_total_return"] is True


def test_eligibility_preserves_product_nullability():
    row = dict(sale_item_id=ITEM, product_id=None, product_name="Produto original",
               quantity_sold=3, quantity_returned=1, max_returnable=2)
    api = API([row])
    assert SupabaseSaleRepository(api, "company").get_returnable_items(SALE) == [row]
    assert api.calls == [("fn_get_returnable_items", {"p_sale_id": SALE})]


def test_empty_eligibility_is_valid():
    assert SupabaseSaleRepository(API([]), "company").get_returnable_items(SALE) == []


@pytest.mark.parametrize("method", ["eligibility", "write"])
def test_sql_permission_error_is_mapped_with_cause(method):
    error = APIError({"code": "42501", "message": "Sem permissão", "details": None, "hint": None})
    api = API(error=error)
    repo = SupabaseSaleRepository(api, "company", role="SELLER")
    with pytest.raises(PermissionDeniedError) as captured:
        if method == "eligibility":
            repo.get_returnable_items(SALE)
        else:
            repo.partial_return(SALE, PAYLOAD, "Defeito", KEY)
    assert captured.value.__cause__ is error
    assert captured.value.role == "SELLER"
    assert len(api.calls) == 1


@pytest.mark.parametrize("error", [
    TimeoutError("Resposta perdida"),
    APIError({"code": "23514", "message": "Quantidade excedida", "details": None, "hint": None}),
    APIError({"code": "40001", "message": "Concorrência", "details": None, "hint": None}),
    APIError({"code": "23503", "message": "Produto inexistente", "details": None, "hint": None}),
])
def test_other_errors_propagate_without_retry(error):
    api = API(error=error)
    with pytest.raises(type(error)) as captured:
        SupabaseSaleRepository(api, "company").partial_return(SALE, PAYLOAD, "Defeito", KEY)
    assert captured.value is error
    assert len(api.calls) == 1


@pytest.mark.parametrize("response", [None, {}, False])
def test_invalid_eligibility_response_is_not_hidden(response):
    api = API(response)
    with pytest.raises(RuntimeError):
        SupabaseSaleRepository(api, "company").get_returnable_items(SALE)
    assert len(api.calls) == 1


def test_old_rpc_response_is_rejected_without_retry():
    api = API(dict(return_id=RETURN, status="COMPLETED", total_amount=10.5))
    with pytest.raises(RuntimeError, match="não repita automaticamente"):
        SupabaseSaleRepository(api, "company").partial_return(SALE, PAYLOAD, "Defeito", KEY)
    assert len(api.calls) == 1


@pytest.mark.parametrize("items", [None, [], [None], [{"quantity": 1}],
                                   [{"sale_item_id": ITEM, "quantity": True}], PAYLOAD * 2])
def test_invalid_request_never_sends_rpc(items):
    api = API()
    with pytest.raises(ValueError):
        SupabaseSaleRepository(api, "company").partial_return(SALE, items, "Defeito", KEY)
    assert not api.calls


@pytest.mark.parametrize("key", [None, "", "not-a-uuid", True, 1])
def test_invalid_key_never_sends_rpc(key):
    api = API()
    with pytest.raises(ValueError, match="UUID"):
        SupabaseSaleRepository(api, "company").partial_return(SALE, PAYLOAD, "Defeito", key)
    assert not api.calls


def test_idempotency_conflict_is_mapped_with_cause_without_retry():
    error = APIError({"code": "PT409", "message": "Conflito", "details": None, "hint": None})
    api = API(error=error)
    with pytest.raises(ValueError, match="conteúdo diferente") as captured:
        SupabaseSaleRepository(api, "company").partial_return(SALE, PAYLOAD, "Defeito", KEY)
    assert captured.value.__cause__ is error
    assert len(api.calls) == 1


def test_repeated_request_always_reaches_database_with_same_key():
    api = API(dict(return_id=RETURN, status="COMPLETED", total_amount="10.50", is_total_return=True))
    repo = SupabaseSaleRepository(api, "company")
    first = repo.partial_return(SALE, PAYLOAD, "Defeito", KEY.upper())
    second = repo.partial_return(SALE, PAYLOAD, "Defeito", KEY)
    assert first == second
    assert len(api.calls) == 2
    assert api.calls[0] == api.calls[1]


def test_mapper_sorts_items_and_normalizes_uuids_like_sql():
    api = API(dict(return_id=RETURN, status="COMPLETED", total_amount="1", is_total_return=False))
    repo = SupabaseSaleRepository(api, "company")
    other = {"sale_item_id": "abcdefab-0000-0000-0000-000000000005", "quantity": 2}
    repo.partial_return(SALE, [other, *PAYLOAD], " Defeito ", KEY.upper())
    repo.partial_return(SALE, [*PAYLOAD, {**other, "sale_item_id": other["sale_item_id"].upper()}], "Defeito", KEY)
    assert api.calls[0] == api.calls[1]
