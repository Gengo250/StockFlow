from decimal import Decimal
from types import SimpleNamespace

import pytest

from stockflow.application.dto.sale_filter import SaleFilter, SalePage
from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.application.services.sale_service import DiscountApprovalRequired, SaleService
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.sale_discount import calculate_discount


class Repository:
    def __init__(self):
        self.calls = []

    def get_discount_limits(self):
        self.calls.append(("limits",))
        return {"ADMIN": None, "SELLER": Decimal("10")}

    def set_discount_limits(self, limits):
        self.calls.append(("set_limits", limits))
        return limits

    def register_multiple(self, *args, **kwargs):
        self.calls.append(("register", args, kwargs))
        return {"total": args[2]}

    def list_all(self):
        self.calls.append(("all",))
        return []

    def list_page(self, filtro, page, size):
        self.calls.append(("page", filtro, page, size))
        return SalePage((), 0, page, size)

    def get(self, sale_id):
        self.calls.append(("get", sale_id))
        return {"id": sale_id}

    def cancel(self, sale_id, reason):
        self.calls.append(("cancel", sale_id, reason))
        raise ValueError("Venda com devolução registrada; utilize o fluxo de devolução por itens")

    def revert(self, sale_id, reason):
        self.calls.append(("revert", sale_id, reason))
        raise ValueError("Venda com devolução registrada; utilize o fluxo de devolução por itens")


def session(role="ADMIN"):
    return SimpleNamespace(role=role, user_id="actor", company_id="company")


def setup(repository=None):
    repo = repository if repository is not None else Repository()
    clients = {"client": SimpleNamespace(client_id="client", active=True)}
    products = {code: SimpleNamespace(code=code, name=code, active=True, sale_price="100", stock="10")
                for code in ("P1", "P2")}
    return SaleService(repo, clients, products), repo


@pytest.mark.parametrize("discount,kind,expected_discount,expected_total", [
    ("0", "FIXED", "50", "150"),
    ("30", "FIXED", "80", "120"),
    ("20", "PERCENTAGE", "80", "120"),
])
def test_register_combines_item_and_sale_discounts_without_losing_original_values(
    discount, kind, expected_discount, expected_total,
):
    service, repo = setup()
    items = (SaleItemInput("P1", 1, "FIXED", Decimal("50")), SaleItemInput("P2", 1))
    result = service.register_multiple(session(), "client", items, "PIX", discount, kind)
    assert result["total"] == Decimal(expected_total)
    operation, args, kwargs = repo.calls[-1]
    assert operation == "register"
    assert args[4] == Decimal(expected_discount)
    assert kwargs["original_total"] == Decimal("200")
    assert kwargs["sale_discount_type"] == kind
    assert kwargs["sale_discount_value"] == Decimal(discount)
    assert kwargs["seller_id"] == "actor"
    assert args[1][0].discount_value == Decimal("50")


def test_register_sale_parses_us22_item_fields_and_defaults_missing_discount_to_zero():
    service, repo = setup()
    service.register_sale(session(), "client", [
        {"codigo": "P1", "quantidade": "1", "discount_type": "PERCENTAGE", "discount_value": "25"},
        {"codigo": "P2", "quantidade": "1"},
    ])
    _, args, kwargs = repo.calls[-1]
    assert args[2] == Decimal("175")
    assert args[1][1].discount_value == Decimal("0")
    assert kwargs["sale_discount_value"] == Decimal("0")


def test_seller_requires_approval_before_write_and_credentials_are_forwarded():
    service, repo = setup()
    items = (SaleItemInput("P1", 1),)
    with pytest.raises(DiscountApprovalRequired):
        service.register_multiple(session("SELLER"), "client", items, discount="20")
    assert all(call[0] != "register" for call in repo.calls)
    credentials = ("admin@example.invalid", "test-only")
    service.register_multiple(session("SELLER"), "client", items, discount="20", approval_credentials=credentials)
    assert repo.calls[-1][2]["approval_credentials"] == credentials


def test_no_discount_sale_does_not_require_approval():
    service, repo = setup()
    service.register_multiple(session("SELLER"), "client", (SaleItemInput("P1", 1),))
    assert repo.calls[-1][1][2] == Decimal("100")
    assert repo.calls[-1][1][4] == 0


@pytest.mark.parametrize("method,args", [
    ("cancel_sale", ("sale", "Defeito")), ("return_sale", ("sale", "Defeito")),
    ("get_discount_limits", ()), ("set_discount_limits", ("10",)),
])
def test_admin_only_operations_deny_before_repository(method, args):
    service, repo = setup()
    with pytest.raises(PermissionDeniedError):
        getattr(service, method)(session("SELLER"), *args)
    assert not repo.calls


@pytest.mark.parametrize("method,operation", [("cancel_sale", "cancel"), ("return_sale", "revert")])
def test_guard_refusal_never_attempts_alternative_operation(method, operation):
    service, repo = setup()
    with pytest.raises(ValueError, match="devolução registrada"):
        getattr(service, method)(session(), "sale", " Defeito ")
    assert repo.calls == [(operation, "sale", "Defeito")]


@pytest.mark.parametrize("reason", [None, "", "\t\n", "x" * 301])
def test_invalid_reversal_reason_does_not_call_repository(reason):
    service, repo = setup()
    with pytest.raises(ValueError):
        service.return_sale(session(), "sale", reason)
    assert not repo.calls


def test_history_preserves_legacy_call_and_supports_authenticated_pagination():
    service, repo = setup()
    assert service.list_sales() == []
    filtro = SaleFilter(sort="VALOR_DESC")
    assert service.list_sales(session(), filtro, 2, 5).page == 2
    assert repo.calls == [("all",), ("page", filtro, 2, 5)]


def test_explicit_missing_session_is_not_treated_as_legacy_history():
    service, repo = setup()
    with pytest.raises(PermissionDeniedError):
        service.list_sales(None)
    assert not repo.calls


@pytest.mark.parametrize("page,size", [(0, 50), (True, 50), (1, 201), (1, False)])
def test_invalid_pagination_is_rejected_before_read(page, size):
    service, repo = setup()
    with pytest.raises(ValueError):
        service.list_sales(session(), page=page, size=size)
    assert not repo.calls


def test_legacy_repository_keeps_supported_contract_but_never_discards_us22_fields():
    class Legacy:
        def __init__(self):
            self.calls = []

        def register_multiple(self, *args):
            self.calls.append(args)
            return {"total": args[2]}

    legacy = Legacy()
    service, _ = setup(legacy)
    service.register_multiple(session(), "client", (SaleItemInput("P1", 1),), discount="5")
    assert legacy.calls[0][2] == Decimal("95")
    with pytest.raises(ValueError, match="US22"):
        service.register_multiple(session(), "client", (SaleItemInput("P1", 1, "FIXED", Decimal("5")),))
    assert len(legacy.calls) == 1


@pytest.mark.parametrize("base,kind,value", [
    ("100", "PERCENTAGE", "101"), ("100", "FIXED", "101"),
    ("100", "FIXED", "NaN"), ("-1", "FIXED", "0"),
])
def test_invalid_discounts_are_rejected(base, kind, value):
    with pytest.raises(ValueError):
        calculate_discount(Decimal(base), kind, Decimal(value))
