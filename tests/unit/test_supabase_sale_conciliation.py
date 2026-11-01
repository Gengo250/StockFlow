from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

from stockflow.application.dto.sale_filter import SaleFilter
from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.application.services.sale_service import DiscountApprovalRequired
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.supabase_sale_repository import SupabaseSaleRepository

SALE = "00000000-0000-0000-0000-000000000001"


class API:
    def __init__(self, responses=None, errors=None):
        self.responses, self.errors = responses or {}, errors or {}
        self.calls = []

    def rpc(self, name, args):
        self.calls.append((name, args))

        def execute():
            if name in self.errors:
                raise self.errors[name]
            return SimpleNamespace(data=self.responses.get(name))

        return SimpleNamespace(execute=execute)

    def table(self, name):
        raise AssertionError("Não deve fazer leitura/escrita extra fora da RPC.")


def error(code, message):
    return APIError({"code": code, "message": message, "details": None, "hint": None})


def receipt(**fields):
    return {
        "id": SALE, "cliente": "Cliente", "total": "120", "discount": "80",
        "original_total": "200", "created_on": "2026-10-30T12:00:00+00:00",
        "items": [{"product_code": "P1", "product_name": "Original", "quantity": 1,
                   "unit_price": "100", "discount_amount": "50"}],
        **fields,
    }


def test_history_keeps_filters_exclusive_end_and_us22_metadata():
    row = receipt(client_name="Cliente", seller_name="Vendedor", total_count=7,
                  status="CONCLUIDA", reversal_kind=None, discount_applied_by_name="Vendedor")
    api = API({"fn_list_sales": [row]})
    page = SupabaseSaleRepository(api, "company").list_page(
        SaleFilter(date_from=date(2026, 10, 1), date_to=date(2026, 10, 30),
                   client_id="client", seller_id="seller", sort="VALOR_DESC"), 2, 3,
    )
    name, args = api.calls[0]
    assert name == "fn_list_sales"
    assert args["p_from"] == "2026-10-01"
    assert args["p_to"] == "2026-10-31"
    assert args["p_limit"] == 3 and args["p_offset"] == 3
    assert args["p_client_id"] == "client" and args["p_seller_id"] == "seller"
    assert page.total == 7 and page.pages == 3
    assert page.rows[0]["original_total"] == "200"
    assert page.rows[0]["discount_applied_by_name"] == "Vendedor"
    assert page.rows[0]["items"][0]["discount_amount"] == "50"


def test_empty_history_and_get_are_valid():
    api = API({"fn_list_sales": []})
    repo = SupabaseSaleRepository(api, "company")
    assert repo.get(SALE) is None
    page = repo.list_page(SaleFilter(), 1, 50)
    assert page.total == 0 and page.pages == 1


@pytest.mark.parametrize("method,rpc", [("cancel", "fn_cancel_sale"), ("revert", "fn_return_sale")])
def test_legacy_reversal_guard_is_business_error_without_fallback(method, rpc):
    original = error("23514", "Venda com devolução registrada; utilize o fluxo de devolução por itens")
    api = API(errors={rpc: original})
    with pytest.raises(ValueError, match="devolução registrada") as captured:
        getattr(SupabaseSaleRepository(api, "company"), method)(SALE, "Defeito")
    assert captured.value.__cause__ is original
    assert api.calls == [(rpc, {"p_sale_id": SALE, "p_reason": "Defeito"})]


@pytest.mark.parametrize("method,rpc", [("cancel", "fn_cancel_sale"), ("revert", "fn_return_sale")])
def test_legacy_reversal_permission_and_unexpected_failures_are_not_hidden(method, rpc):
    api = API(errors={rpc: error("42501", "Sem permissão")})
    with pytest.raises(PermissionDeniedError):
        getattr(SupabaseSaleRepository(api, "company"), method)(SALE, "Defeito")
    unknown = error("40001", "Concorrência")
    api.errors[rpc] = unknown
    with pytest.raises(APIError) as captured:
        getattr(SupabaseSaleRepository(api, "company"), method)(SALE, "Defeito")
    assert captured.value is unknown
    assert len(api.calls) == 2


def test_register_preserves_us22_arguments_and_receipt():
    api = API({"fn_register_sale_with_discounts": receipt(discount_authorized_by="admin")})
    repo = SupabaseSaleRepository(api, "company")
    result = repo.register_multiple(
        SimpleNamespace(client_id="client"),
        (SaleItemInput("P1", 1, "FIXED", Decimal("50")),), Decimal("120"), "PIX", Decimal("80"),
        original_total=Decimal("200"), sale_discount_type="PERCENTAGE",
        sale_discount_value=Decimal("20"), seller_id="seller",
    )
    assert api.calls == [("fn_register_sale_with_discounts", {
        "p_company_id": "company", "p_client_id": "client",
        "p_items": [{"product_code": "P1", "quantity": 1, "discount_type": "FIXED", "discount_value": "50"}],
        "p_payment_method": "PIX", "p_sale_discount_type": "PERCENTAGE",
        "p_sale_discount_value": "20", "p_seller_id": "seller",
    })]
    assert result["total"] == "120.00"
    assert result["discount"] == "80" and result["original_total"] == "200"
    assert result["discount_authorized_by"] == "admin"


@pytest.mark.parametrize("discount,expected", [(Decimal("0"), "0"), (Decimal("5"), "5"), (None, "0")])
def test_legacy_call_uses_fixed_sale_discount_without_old_rpc_fallback(discount, expected):
    api = API({"fn_register_sale_with_discounts": receipt()})
    SupabaseSaleRepository(api, "company").register_multiple(
        SimpleNamespace(client_id="client"), (SaleItemInput("P1", 1),), Decimal("1"), discount=discount,
    )
    assert len(api.calls) == 1
    assert api.calls[0][0] == "fn_register_sale_with_discounts"
    assert api.calls[0][1]["p_sale_discount_value"] == expected


def test_item_discount_requires_separate_sale_discount_at_repository_boundary():
    api = API()
    with pytest.raises(ValueError, match="separadamente"):
        SupabaseSaleRepository(api, "company").register_multiple(
            SimpleNamespace(client_id="client"),
            (SaleItemInput("P1", 1, "FIXED", Decimal("5")),), Decimal("1"),
        )
    assert api.calls == []


def test_discount_approval_request_and_timeout_do_not_retry():
    rpc = "fn_register_sale_with_discounts"
    api = API(errors={rpc: error("42501", "aprovação de ADMIN necessária")})
    repo = SupabaseSaleRepository(api, "company")
    with pytest.raises(DiscountApprovalRequired):
        repo.register_multiple(SimpleNamespace(client_id="client"), (SaleItemInput("P1", 1),), Decimal("1"))
    api.errors[rpc] = TimeoutError("Resposta perdida")
    with pytest.raises(TimeoutError):
        repo.register_multiple(SimpleNamespace(client_id="client"), (SaleItemInput("P1", 1),), Decimal("1"))
    assert len(api.calls) == 2


@pytest.mark.parametrize("role,company,allowed", [
    ("ADMIN", "company", True), ("SELLER", "company", False), ("ADMIN", "other", False),
])
def test_approval_uses_independent_authenticated_admin_client(monkeypatch, role, company, allowed):
    main = API()
    independent = API({
        "fn_current_user_id": "admin", "fn_my_companies": [{"company_id": company, "user_role": role}],
        "fn_register_sale_with_discounts": receipt(),
    })
    independent.auth = SimpleNamespace(sign_in_with_password=lambda _: SimpleNamespace(user=object()))
    monkeypatch.setattr(
        "stockflow.infrastructure.database.supabase_client.create_independent_auth_client", lambda: independent,
    )
    repo = SupabaseSaleRepository(main, "company")
    args = (SimpleNamespace(client_id="client"), (SaleItemInput("P1", 1),), Decimal("1"))
    if allowed:
        repo.register_multiple(*args, approval_credentials=("admin@example.invalid", "test-only"))
        assert independent.calls[-1][0] == "fn_register_sale_with_discounts"
    else:
        with pytest.raises(ValueError, match="mesma empresa"):
            repo.register_multiple(*args, approval_credentials=("admin@example.invalid", "test-only"))
        assert all(name != "fn_register_sale_with_discounts" for name, _ in independent.calls)
    assert not main.calls


def test_independent_auth_factory_disables_persistence_without_replacing_main_client(monkeypatch):
    from stockflow.infrastructure.database import supabase_client as module
    import supabase

    main, independent = object(), object()
    calls = []
    monkeypatch.setattr(module, "_client", main)
    monkeypatch.setattr(module, "_credenciais", lambda: ("https://example.invalid", "test-publishable"))
    def create(url, key, **kwargs):
        calls.append(kwargs)
        return independent
    monkeypatch.setattr(supabase, "create_client", create)
    assert module.create_independent_auth_client() is independent
    assert module._client is main
    assert calls[0]["options"].persist_session is False
    assert calls[0]["options"].auto_refresh_token is False
