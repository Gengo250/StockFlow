import pytest

from stockflow.application.dto.purchase_input import PurchaseInput, PurchaseItemInput
from stockflow.domain.enums.purchase_status import PurchaseStatus
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.supabase_purchase_repository import (
    SupabasePurchaseRepository,
)


COMPANY = "company-test"
PURCHASE = "purchase-test"


class Response:
    def __init__(self, data):
        self.data = data


class PostgrestError(Exception):
    def __init__(self, message, code=""):
        super().__init__(message)
        self.code = code


class Client:
    def __init__(self, results=None, errors=None):
        self.results = results or {}
        self.errors = errors or {}
        self.calls = []

    def rpc(self, name, args):
        self.calls.append((name, args))
        if name in self.errors:
            raise self.errors[name]
        return Rpc(self.results.get(name))


class Rpc:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return Response(self.data)


def test_create_and_receive_use_atomic_purchase_rpcs():
    client = Client({"fn_create_purchase": PURCHASE})
    repository = SupabasePurchaseRepository(client, COMPANY, role="ADMIN")
    data = PurchaseInput("supplier-1", (
        PurchaseItemInput("PRD-001", 3),
        PurchaseItemInput("PRD-002", 2),
    ))

    assert repository.create(data) == PURCHASE
    repository.receive(PURCHASE)

    assert client.calls == [
        (
            "fn_create_purchase",
            {
                "p_company_id": COMPANY,
                "p_supplier_id": "supplier-1",
                "p_items": [
                    {"product_code": "PRD-001", "quantity": 3},
                    {"product_code": "PRD-002", "quantity": 2},
                ],
            },
        ),
        ("fn_receive_purchase", {"p_purchase_id": PURCHASE}),
    ]


def test_list_maps_supplier_status_and_items():
    client = Client({
        "fn_list_company_purchases": [{
            "id": PURCHASE,
            "supplier_id": "supplier-1",
            "supplier_name": "Fornecedor",
            "status": "RASCUNHO",
            "created_on": "2026-11-11T12:00:00+00:00",
            "received_on": None,
            "items": [{
                "product_code": "PRD-001",
                "product_name": "Produto",
                "quantity": 4,
            }],
        }],
    })

    purchase = SupabasePurchaseRepository(client, COMPANY).list_all()[0]

    assert purchase.purchase_id == PURCHASE
    assert purchase.status is PurchaseStatus.RASCUNHO
    assert purchase.supplier_name == "Fornecedor"
    assert purchase.items[0].product_code == "PRD-001"
    assert purchase.items[0].quantity == 4
    assert client.calls == [
        ("fn_list_company_purchases", {"p_company_id": COMPANY})
    ]


def test_permission_denial_is_translated_and_other_errors_propagate():
    denied = PostgrestError("Sem permissão para receber compras", "42501")
    client = Client(errors={"fn_receive_purchase": denied})

    with pytest.raises(PermissionDeniedError, match="receber compras"):
        SupabasePurchaseRepository(client, COMPANY, role="SELLER").receive(PURCHASE)

    unexpected = PostgrestError("database unavailable", "08006")
    client = Client(errors={"fn_receive_purchase": unexpected})
    with pytest.raises(PostgrestError) as error:
        SupabasePurchaseRepository(client, COMPANY).receive(PURCHASE)
    assert error.value is unexpected
