from dataclasses import replace
from types import SimpleNamespace

import pytest

from stockflow.application.dto.purchase_input import PurchaseInput, PurchaseItemInput
from stockflow.application.services.purchase_service import PurchaseService
from stockflow.domain.enums.purchase_status import PurchaseStatus
from stockflow.domain.entities.supplier import Supplier
from stockflow.domain.permissions import can_manage_purchases
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_movement_repository import (
    DemoMovementRepository,
)
from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.infrastructure.repositories.demo_purchase_repository import (
    DemoPurchaseRepository,
)
from stockflow.infrastructure.repositories.demo_supplier_repository import (
    DemoSupplierRepository,
)
from stockflow.presentation.demo_products import Product


def product(code, stock="4", maximum=None, active=True):
    return Product(
        code, code, "Eletrônicos", "UN", "10,00", "5,00", active,
        stock, "Normal", maximum_stock=maximum,
    )


@pytest.fixture
def setup():
    products = {
        "PRD-001": product("PRD-001", maximum=20),
        "PRD-002": product("PRD-002", stock="2", maximum=20),
    }
    suppliers = DemoSupplierRepository({
        "FOR-001": Supplier("FOR-001", "Fornecedor ativo"),
        "FOR-002": Supplier("FOR-002", "Fornecedor inativo", active=False),
    })
    movements = DemoMovementRepository(products, suppliers=suppliers)
    repository = DemoPurchaseRepository(products, suppliers, movements)
    product_repository = DemoProductRepository(products)
    service = PurchaseService(repository, suppliers, product_repository)
    admin = SimpleNamespace(role="ADMIN")
    return products, suppliers, movements, repository, service, admin


def test_purchase_workflow_creates_draft_then_one_confirmed_entry_per_item(setup):
    products, _, movements, repository, service, admin = setup
    before = {code: item.stock for code, item in products.items()}
    data = PurchaseInput("FOR-001", (
        PurchaseItemInput("PRD-001", 3),
        PurchaseItemInput("PRD-002", 1),
    ))

    purchase_id = service.create(admin, data)
    purchase = repository.list_all()[0]
    assert purchase.status is PurchaseStatus.RASCUNHO
    assert {code: item.stock for code, item in products.items()} == before
    assert movements.list_movements() == ()

    service.receive(admin, purchase_id)

    received = repository.list_all()[0]
    assert received.status is PurchaseStatus.RECEBIDA
    assert int(products["PRD-001"].stock) == 7
    assert int(products["PRD-002"].stock) == 3
    rows = movements._movements
    assert len(rows) == 2
    assert all(row["status"] == "CONFIRMADA" for row in rows)
    assert all(row["supplier_id"] == "FOR-001" for row in rows)
    assert all(row["purchase_id"] == purchase_id for row in rows)

    with pytest.raises(ValueError, match="rascunho"):
        service.receive(admin, purchase_id)
    assert len(movements._movements) == 2


def test_failed_purchase_receipt_keeps_all_stock_and_status_unchanged(setup):
    products, _, movements, repository, service, admin = setup
    products["PRD-002"] = replace(
        products["PRD-002"], maximum_stock=2
    )
    purchase_id = service.create(
        admin,
        PurchaseInput("FOR-001", (
            PurchaseItemInput("PRD-001", 2),
            PurchaseItemInput("PRD-002", 1),
        )),
    )
    before = {code: item.stock for code, item in products.items()}

    with pytest.raises(ValueError, match="máximo"):
        service.receive(admin, purchase_id)

    assert {code: item.stock for code, item in products.items()} == before
    assert movements.list_movements() == ()
    assert repository.list_all()[0].status is PurchaseStatus.RASCUNHO


def test_demo_receipt_rolls_back_if_a_movement_fails_mid_batch(setup, monkeypatch):
    products, _, movements, repository, service, admin = setup
    purchase_id = service.create(
        admin,
        PurchaseInput("FOR-001", (
            PurchaseItemInput("PRD-001", 2),
            PurchaseItemInput("PRD-002", 1),
        )),
    )
    before = {code: item.stock for code, item in products.items()}
    register = movements.register
    attempts = 0

    def fail_on_second_movement(data):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("falha simulada ao gravar movimento")
        return register(data)

    monkeypatch.setattr(movements, "register", fail_on_second_movement)

    with pytest.raises(RuntimeError, match="falha simulada"):
        service.receive(admin, purchase_id)

    assert {code: item.stock for code, item in products.items()} == before
    assert movements.list_movements() == ()
    assert repository.list_all()[0].status is PurchaseStatus.RASCUNHO


@pytest.mark.parametrize(
    ("supplier_id", "items", "message"),
    [
        ("FOR-002", (PurchaseItemInput("PRD-001", 1),), "fornecedor ativo"),
        ("FOR-001", (), "pelo menos um item"),
        ("FOR-001", (PurchaseItemInput("PRD-404", 1),), "produto ativo"),
        ("FOR-001", (PurchaseItemInput("PRD-001", 0),), "inteiro positivo"),
        ("FOR-001", (PurchaseItemInput("PRD-001", 1_000_001),), "exceder"),
    ],
)
def test_invalid_purchase_is_rejected_before_creation(setup, supplier_id, items, message):
    _, _, _, repository, service, admin = setup

    with pytest.raises(ValueError, match=message):
        service.create(admin, PurchaseInput(supplier_id, items))

    assert repository.list_all() == ()


def test_seller_cannot_manage_purchases(setup):
    _, _, _, _, service, _ = setup
    seller = SimpleNamespace(role="SELLER")

    assert can_manage_purchases(seller) is False
    with pytest.raises(PermissionDeniedError, match="permiss"):
        service.list_purchases(seller)


def test_demo_repository_refuses_inactive_product_at_receipt(setup):
    products, _, _, repository, service, admin = setup
    purchase_id = service.create(
        admin, PurchaseInput("FOR-001", (PurchaseItemInput("PRD-001", 1),))
    )
    products["PRD-001"] = replace(products["PRD-001"], active=False)

    with pytest.raises(ValueError, match="produto inativo"):
        repository.receive(purchase_id)

    assert repository.list_all()[0].status is PurchaseStatus.RASCUNHO
