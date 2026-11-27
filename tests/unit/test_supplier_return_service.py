from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from stockflow.application.dto.purchase_input import PurchaseInput, PurchaseItemInput
from stockflow.application.dto.supplier_return_input import SupplierReturnInput, SupplierReturnItemInput
from stockflow.application.services.supplier_return_service import SupplierReturnService
from stockflow.domain.entities.supplier import Supplier
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
from stockflow.infrastructure.repositories.demo_purchase_repository import DemoPurchaseRepository
from stockflow.infrastructure.repositories.demo_supplier_repository import DemoSupplierRepository
from stockflow.infrastructure.repositories.demo_supplier_return_repository import DemoSupplierReturnRepository
from stockflow.presentation.demo_products import Product


def line(code="P1", quantity=1, reason="Produto avariado"):
    return SupplierReturnItemInput(code, quantity, reason)


def request(*items, **kwargs):
    return SupplierReturnInput("S1", tuple(items or (line(),)), **kwargs)


@pytest.fixture
def setup():
    products = {code: Product(code, "Produto " + code, "Categoria", "UN", "10", "5", True,
                              stock, "Normal", supplier_id="S2")
                for code, stock in (("P1", "8"), ("P2", "4"))}
    suppliers = DemoSupplierRepository({"S1": Supplier("S1", "Fornecedor da devolução"),
                                        "S2": Supplier("S2", "Outro fornecedor")})
    movements = DemoMovementRepository(products, suppliers=suppliers,
                                       agora=datetime(2026, 11, 27, tzinfo=timezone.utc))
    purchases = DemoPurchaseRepository(products, suppliers, movements)
    repo = DemoSupplierReturnRepository(products, suppliers, movements, purchases,
                                        company_id="C1", actor_id="U1", actor_name="Responsável")
    session = SimpleNamespace(role="ADMIN", company_id="C1", user_id="U1")
    return SimpleNamespace(products=products, suppliers=suppliers, movements=movements,
                           purchases=purchases, repo=repo,
                           service=SupplierReturnService(repo, session), session=session)


@pytest.mark.parametrize("role", ["ADMIN", "STOCK"])
def test_authorized_return_has_one_exit_per_item_and_traceable_history(setup, role):
    setup.session.role = role
    result = setup.service.create_return(request(line(quantity=3), line("P2", 2, "Recebimento incorreto")))
    assert [setup.products[code].stock for code in ("P1", "P2")] == ["5", "2"]
    assert result.supplier_id == "S1"
    assert result.purchase_id is None
    assert result.created_by == "U1"
    assert result.created_by_name == "Responsável"
    assert result.created_on == "2026-11-27T00:00:00+00:00"
    assert setup.service.get_return(result.return_id) == result
    assert setup.service.list_returns() == (result,)
    for item, movement in zip(result.items, setup.movements._movements):
        assert movement["id"] == item.movement_id
        assert movement["supplier_return_item_id"] == item.item_id
        assert movement["supplier_return_id"] == result.return_id
        assert movement["supplier_id"] == "S1"
        assert movement["kind"] == "SAIDA"
        assert movement["status"] == "CONFIRMADA"
        assert movement["created_by"] == "U1"
        assert movement["confirmed_on"] is not None
        assert item.reason in movement["note"]


@pytest.mark.parametrize("session", [None, SimpleNamespace(role="SELLER", company_id="C1", user_id="U1"),
    SimpleNamespace(role="ADMIN", company_id="", user_id="U1"),
    SimpleNamespace(role="ADMIN", company_id="C1", user_id=None),
    SimpleNamespace(role="ADMIN", company_id="C2", user_id="U1"),
    SimpleNamespace(role="ADMIN", company_id="C1", user_id="U2")])
def test_unauthorized_operations_stop_before_repository_access(session):
    repo = Mock(company_id="C1", actor_id="U1")
    service = SupplierReturnService(repo, session)
    for operation in (lambda: service.create_return(request()),
                      lambda: service.get_return("R1"), service.list_returns):
        with pytest.raises(PermissionDeniedError):
            operation()
    assert repo.mock_calls == []


@pytest.mark.parametrize("data", [
    SupplierReturnInput("", (line(),)), SupplierReturnInput("S1", ()),
    request(purchase_id=" "), request(idempotency_key="invalid"),
    request(line(code="")), request(line(quantity=0)), request(line(quantity=-1)),
    request(line(quantity=True)), request(line(quantity=1.5)), request(line(quantity=1_000_001)),
    request(line(reason="  ")), request(line(reason="x" * 1001)),
    SupplierReturnInput("S1", (line(),) * 101),
])
def test_invalid_input_is_rejected_without_any_write(setup, data):
    before = deepcopy(setup.products)
    with pytest.raises(ValueError):
        setup.service.create_return(data)
    assert setup.products == before
    assert setup.movements._movements == []
    assert setup.repo.list_all() == ()


def test_duplicate_product_lines_are_aggregated_for_stock_validation(setup):
    with pytest.raises(ValueError, match="insuficiente"):
        setup.service.create_return(request(line(quantity=5), line(quantity=4, reason="Outro motivo")))
    assert setup.products["P1"].stock == "8"
    assert setup.movements._movements == []
    assert setup.repo.list_all() == ()


def test_retry_uses_same_record_and_never_reduces_stock_twice(setup):
    data = request(line(quantity=3))
    first = setup.service.create_return(data)
    assert setup.service.create_return(data) is first
    assert setup.products["P1"].stock == "5"
    assert len(setup.movements._movements) == 1
    with pytest.raises(ValueError, match="outra requisição"):
        setup.service.create_return(replace(data, items=(line(quantity=2),)))
    assert setup.products["P1"].stock == "5"


def test_failure_on_second_stock_write_restores_entire_operation(setup, monkeypatch):
    before = deepcopy(setup.products)
    apply = setup.movements._aplicar_no_saldo
    attempts = []
    def fail_second(row, sentido):
        attempts.append(row["product_code"])
        if len(attempts) == 2:
            raise RuntimeError("falha simulada no segundo item")
        apply(row, sentido)
    monkeypatch.setattr(setup.movements, "_aplicar_no_saldo", fail_second)
    with pytest.raises(RuntimeError, match="segundo item"):
        setup.service.create_return(request(line(), line("P2")))
    assert attempts == ["P1", "P2"]
    assert setup.products == before
    assert setup.movements._movements == []
    assert setup.repo.list_all() == ()
    assert setup.repo._requests == {}


def test_failure_while_publishing_history_also_restores_stock(setup, monkeypatch):
    import stockflow.infrastructure.repositories.demo_supplier_return_repository as module
    before = deepcopy(setup.products)
    def fail(*args, **kwargs):
        raise RuntimeError("histórico indisponível")
    monkeypatch.setattr(module, "SupplierReturn", fail)
    with pytest.raises(RuntimeError, match="histórico"):
        setup.service.create_return(request())
    assert setup.products == before
    assert setup.movements._movements == []
    assert setup.repo.list_all() == ()
    assert setup.repo._requests == {}


def test_origin_must_be_received_and_match_supplier_and_product(setup):
    purchase_id = setup.purchases.create(PurchaseInput("S1", (PurchaseItemInput("P1", 2),)))
    data = request(purchase_id=purchase_id)
    with pytest.raises(ValueError, match="recebida"):
        setup.service.create_return(data)
    setup.purchases.receive(purchase_id)
    with pytest.raises(ValueError, match="compra de origem"):
        setup.service.create_return(request(line("P2"), purchase_id=purchase_id))
    with pytest.raises(ValueError, match="fornecedor"):
        setup.service.create_return(replace(data, supplier_id="S2"))
    result = setup.service.create_return(data)
    assert result.purchase_id == purchase_id
    assert setup.products["P1"].stock == "9"
    assert setup.movements._movements[-1]["purchase_id"] == purchase_id


def test_inactivation_does_not_prevent_returning_existing_stock(setup):
    setup.products["P1"] = replace(setup.products["P1"], active=False)
    setup.suppliers.get("S1").active = False
    setup.service.create_return(request())
    assert setup.products["P1"].stock == "7"
    assert setup.products["P1"].active is False


def test_supplier_return_exit_cannot_be_canceled_individually(setup):
    result = setup.service.create_return(request())
    with pytest.raises(ValueError, match="isoladamente"):
        setup.movements.cancel(result.items[0].movement_id)
    assert setup.products["P1"].stock == "7"
    assert setup.movements._movements[0]["status"] == "CONFIRMADA"


def test_history_filters_pagination_and_input_normalization(setup):
    first = setup.service.create_return(request(line(code=" P1 ", reason="  Avaria  ")))
    second = setup.service.create_return(SupplierReturnInput("S2", (line("P2"),)))
    assert first.items[0].reason == "Avaria"
    assert setup.service.list_returns(supplier_id=" S1 ") == (first,)
    ordered = tuple(sorted((first, second), key=lambda row: (row.created_on, row.return_id), reverse=True))
    assert setup.service.list_returns(limit=1) == ordered[:1]
    assert setup.service.list_returns(limit=1, offset=1) == ordered[1:]
    for kwargs in ({"limit": 0}, {"limit": 201}, {"limit": True}, {"offset": -1}, {"supplier_id": " "}):
        with pytest.raises(ValueError):
            setup.service.list_returns(**kwargs)



def test_backend_factory_reuses_existing_demo_catalog_purchase_and_ledger(setup, monkeypatch):
    from stockflow.presentation import backend
    monkeypatch.setattr(backend, "using_supabase", lambda: False)
    setup.session.name = "Responsável"
    service = backend.build_supplier_return_service(setup.session, setup.products, setup.suppliers,
                                                    setup.movements, setup.purchases)
    assert service.repository.products is setup.products
    assert service.repository.movements is setup.movements
    assert service.repository.purchases is setup.purchases
    service.create_return(request())
    assert setup.products["P1"].stock == "7"
    assert len(setup.movements._movements) == 1


def test_backend_factory_blocks_seller_before_accessing_any_client(monkeypatch):
    from stockflow.presentation import backend
    client = Mock()
    monkeypatch.setattr(backend, "_client", client)
    with pytest.raises(PermissionDeniedError):
        backend.build_supplier_return_service(SimpleNamespace(role="SELLER", company_id="C1", user_id="U1"))
    client.assert_not_called()
