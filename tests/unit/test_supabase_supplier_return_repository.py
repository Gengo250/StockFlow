from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from stockflow.application.dto.supplier_return_input import SupplierReturnInput, SupplierReturnItemInput
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.supabase_supplier_return_repository import (
    SupabaseSupplierReturnRepository, parse_supplier_return,
)


class Client:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def rpc(self, name, args):
        self.calls.append((name, args))
        def execute():
            if self.error:
                raise self.error
            return SimpleNamespace(data=self.result)
        return SimpleNamespace(execute=execute)


class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def response():
    return {"id": str(uuid4()), "company_id": str(uuid4()), "supplier_id": str(uuid4()),
            "supplier_name": "Fornecedor", "purchase_id": str(uuid4()), "created_by": str(uuid4()),
            "created_by_name": "Estoquista", "created_on": "2026-11-27T00:00:00+00:00",
            "idempotency_key": str(uuid4()), "items": [{"id": str(uuid4()), "product_code": "P1",
            "product_name": "Produto", "quantity": 2, "reason": "Avaria", "movement_id": str(uuid4())}]}


def test_creation_uses_only_atomic_rpc_and_identity_is_not_client_supplied():
    row = response()
    client = Client(row)
    repo = SupabaseSupplierReturnRepository(client, row["company_id"], role="STOCK")
    data = SupplierReturnInput(row["supplier_id"], (SupplierReturnItemInput("P1", 2, "Avaria"),),
                               row["purchase_id"], row["idempotency_key"])
    result = repo.create(data)
    assert client.calls == [("fn_register_supplier_return", {
        "p_company_id": row["company_id"], "p_supplier_id": row["supplier_id"],
        "p_purchase_id": row["purchase_id"], "p_idempotency_key": row["idempotency_key"],
        "p_items": [{"product_code": "P1", "quantity": 2, "reason": "Avaria"}]})]
    assert result.return_id == row["id"]
    assert result.created_by == row["created_by"]
    assert result.created_by_name == "Estoquista"
    assert result.items[0].movement_id == row["items"][0]["movement_id"]


def test_history_get_and_combined_filters_use_authorized_rpcs():
    row = response()
    client = Client(row)
    repo = SupabaseSupplierReturnRepository(client, row["company_id"])
    assert repo.get(row["id"]).return_id == row["id"]
    client.result = [row]
    assert repo.list_all(supplier_id=row["supplier_id"], purchase_id=row["purchase_id"], limit=10, offset=5)[0].return_id == row["id"]
    assert client.calls == [
        ("fn_get_supplier_return", {"p_company_id": row["company_id"], "p_id": row["id"]}),
        ("fn_list_supplier_returns", {"p_company_id": row["company_id"], "p_supplier_id": row["supplier_id"],
            "p_purchase_id": row["purchase_id"], "p_limit": 10, "p_offset": 5})]


@pytest.mark.parametrize("code,exception", [("42501", PermissionDeniedError), ("23514", ValueError),
                                          ("23503", ValueError), ("22023", ValueError), ("08006", ApiError)])
def test_refusal_or_transport_failure_is_never_reported_as_success(code, exception):
    row = response()
    error = ApiError(code, "operação recusada")
    client = Client(error=error)
    repo = SupabaseSupplierReturnRepository(client, row["company_id"], role="SELLER")
    with pytest.raises(exception):
        repo.create(SupplierReturnInput(row["supplier_id"], (SupplierReturnItemInput("P1", 1, "Avaria"),)))
    assert len(client.calls) == 1


@pytest.mark.parametrize("change", [lambda row: row.update(items=[]), lambda row: row.update(created_by=None),
    lambda row: row.update(company_id=None), lambda row: row.update(id="invalid"),
    lambda row: row["items"][0].update(quantity=True), lambda row: row["items"][0].update(quantity=0),
    lambda row: row["items"][0].update(reason=" "), lambda row: row["items"][0].update(movement_id=None)])
def test_malformed_response_is_not_accepted_as_a_completed_return(change):
    row = deepcopy(response())
    change(row)
    with pytest.raises(RuntimeError, match="histórico"):
        parse_supplier_return(row)


def test_missing_history_response_is_distinct_from_empty_history():
    client = Client(None)
    repo = SupabaseSupplierReturnRepository(client, str(uuid4()))
    with pytest.raises(RuntimeError, match="inválida"):
        repo.list_all()
    client.result = []
    assert repo.list_all() == ()
