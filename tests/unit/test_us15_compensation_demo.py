"""Paridade Demo/SQL para restituição integral e falhas transacionais US15."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest

from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
from stockflow.presentation.demo_products import Product


def make_sale(*, repeated=False, multiple=False):
    session = SimpleNamespace(role="ADMIN", user_id="admin", company_id="company", name="Admin auditor")
    products = {code: Product(code, code, "Cat", "UN", "10.00", "0", True, "10", "Normal") for code in ("A", "B")}
    movements = DemoMovementRepository(products)
    repository = DemoSaleRepository(products, movements, session=session)
    items = [SaleItemInput("A", 2)]
    if repeated:
        items = [SaleItemInput("A", 1), SaleItemInput("A", 2)]
    if multiple:
        items.append(SaleItemInput("B", 2))
    row = repository.register_multiple(SimpleNamespace(name="Cliente"), tuple(items), Decimal(10 * sum(item.quantity for item in items)))
    return repository, row


def state(repository):
    return deepcopy((repository.rows, repository._products, repository.movements._movements,
                     repository._return_sales, repository._returns, repository._return_requests))


def test_cancellation_links_each_item_and_preserves_outputs_and_financial_values():
    repository, row = make_sale()
    original_row = deepcopy(row)
    original_movements = deepcopy(repository.movements._movements)
    result = repository.cancel(row["id"], "  Registro incorreto  ")
    assert result["status"] == "CANCELADA" and result["reversal_reason"] == "Registro incorreto"
    assert result["reversal_by"] == "Admin auditor" and result["reversal_by_id"] == "admin"
    assert result["reversal_on"]
    for key in ("items", "total", "discount", "payment_method"):
        assert result[key] == original_row[key]
    assert repository.returns == ()
    assert repository.movements._movements[:len(original_movements)] == original_movements
    entry, = repository.movements._movements[len(original_movements):]
    assert entry["kind"] == "ENTRADA" and entry["status"] == "CONFIRMADA"
    assert entry["cancellation_id"] == result["reversal_id"]
    assert entry["sale_item_id"] == row["items"][0]["id"]
    assert entry["sale_id"] == row["id"] and entry["return_id"] is None
    assert entry["created_by"] == "admin" and entry["company_id"] == "company"
    assert entry["created_on"] and entry["confirmed_on"]
    assert repository._products["A"].stock == "10"
    before_repeat = state(repository)
    with pytest.raises(ValueError, match="já foi"):
        repository.cancel(row["id"], "Tentativa repetida")
    assert state(repository) == before_repeat


def test_repeated_product_lines_keep_one_output_and_compensation_per_item():
    repository, row = make_sale(repeated=True)
    outputs = deepcopy(repository.movements._movements)
    repository.cancel(row["id"], "Registro incorreto")
    entries = [movement for movement in repository.movements._movements if movement.get("cancellation_id")]
    assert len(outputs) == len(entries) == 2
    assert {movement["sale_item_id"]: movement["quantity"] for movement in entries} == {item["id"]: item["quantity"] for item in row["items"]}
    assert repository.movements._movements[:2] == outputs
    assert repository._products["A"].stock == "10"


@pytest.mark.parametrize("role,user,company", [
    ("SELLER", "seller", "company"), ("STOCK", "stock", "company"),
    ("ADMIN", "", "company"), ("ADMIN", "admin", ""), ("ADMIN", None, "company"),
])
def test_direct_adapter_refuses_missing_authority_or_identity(role, user, company):
    repository, row = make_sale()
    repository._session = SimpleNamespace(role=role, user_id=user, company_id=company)
    before = state(repository)
    with pytest.raises(PermissionDeniedError):
        repository.cancel(row["id"], "Registro incorreto")
    assert state(repository) == before


@pytest.mark.parametrize("method", ["cancel", "revert"])
def test_previous_us20_return_blocks_whole_sale_operation(method):
    repository, row = make_sale()
    repository.partial_return(row["id"], [{"sale_item_id": row["items"][0]["id"], "quantity": 1}], "Defeito", str(uuid4()))
    before = state(repository)
    with pytest.raises(ValueError, match="devolução registrada"):
        getattr(repository, method)(row["id"], "Operação indevida")
    assert state(repository) == before
    assert repository._products["A"].stock == "9"


@pytest.mark.parametrize("failure_step", [1, 2])
def test_failure_after_restock_rolls_back_and_allows_clean_retry(monkeypatch, failure_step):
    repository, row = make_sale(multiple=True)
    before = state(repository)
    original = repository.movements._aplicar_no_saldo
    count = 0
    def fail(movement, sentido):
        nonlocal count
        original(movement, sentido)
        count += 1
        if count == failure_step:
            raise RuntimeError("Falha após restituição")
    monkeypatch.setattr(repository.movements, "_aplicar_no_saldo", fail)
    with pytest.raises(RuntimeError, match="após restituição"):
        repository.cancel(row["id"], "Registro incorreto")
    assert state(repository) == before
    monkeypatch.setattr(repository.movements, "_aplicar_no_saldo", original)
    repository.cancel(row["id"], "Registro incorreto")
    assert repository._products["A"].stock == repository._products["B"].stock == "10"


def test_failure_after_audit_publication_rolls_back_stock_sale_and_snapshot(monkeypatch):
    repository, row = make_sale(multiple=True)
    before = state(repository)
    original = repository.movements.reverse_sale
    def fail(*args, **kwargs):
        publish = kwargs["publish"]
        def late_failure():
            publish()
            raise RuntimeError("Falha após auditoria")
        kwargs["publish"] = late_failure
        return original(*args, **kwargs)
    monkeypatch.setattr(repository.movements, "reverse_sale", fail)
    with pytest.raises(RuntimeError, match="após auditoria"):
        repository.cancel(row["id"], "Registro incorreto")
    assert state(repository) == before


@pytest.mark.parametrize("corruption", ["missing_link", "wrong_company", "quantity", "status", "missing_product", "extra_output"])
def test_inconsistent_outputs_are_rejected_without_inference(corruption):
    repository, row = make_sale()
    output = repository.movements._movements[0]
    if corruption == "missing_link":
        output.pop("sale_item_id")
    elif corruption == "wrong_company":
        output["company_id"] = "other-company"
    elif corruption == "quantity":
        output["quantity"] += 1
    elif corruption == "status":
        output["status"] = "CANCELADA"
    elif corruption == "missing_product":
        repository._products.pop("A")
    else:
        repository.movements._movements.append(dict(output, id="extra-output"))
    before = state(repository)
    with pytest.raises(ValueError):
        repository.cancel(row["id"], "Registro incorreto")
    assert state(repository) == before


def test_inactive_product_is_restocked_without_reactivation():
    repository, row = make_sale()
    repository._products["A"] = replace(repository._products["A"], active=False)
    repository.cancel(row["id"], "Registro incorreto")
    assert repository._products["A"].stock == "10"
    assert repository._products["A"].active is False


def test_stock_limit_checks_total_of_repeated_product_lines_atomically():
    repository, row = make_sale(repeated=True)
    repository._products["A"] = replace(repository._products["A"], maximum_stock=9)
    before = state(repository)
    with pytest.raises(ValueError, match="máximo"):
        repository.cancel(row["id"], "Registro incorreto")
    assert state(repository) == before


@pytest.mark.parametrize("scenario", ["cancel_cancel", "cancel_return"])
def test_demo_concurrent_operations_never_restock_twice(scenario):
    repository, row = make_sale()
    barrier = Barrier(2)
    def worker(index):
        barrier.wait(timeout=10)
        try:
            if index == 0 or scenario == "cancel_cancel":
                repository.cancel(row["id"], "Registro incorreto")
            else:
                repository.partial_return(row["id"], [{"sale_item_id": row["items"][0]["id"], "quantity": 1}], "Defeito", str(uuid4()))
            return "ok"
        except ValueError:
            return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, range(2))) == ["ok", "rejected"]
    assert repository._products["A"].stock == ("10" if row["status"] == "CANCELADA" else "9")
