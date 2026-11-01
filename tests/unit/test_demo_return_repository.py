from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
from stockflow.infrastructure.repositories.supabase_sale_repository import SupabaseSaleRepository
from stockflow.presentation.demo_products import Product


def setup_sale(*, quantity=3, price="1.00", discount="0.01", second=False, company_max=None):
    admin = SimpleNamespace(role="ADMIN", user_id="admin", company_id="company")
    products = {
        "P1": Product("P1", "Produto original", "Categoria", "UN", price, "0", True, "10", "Normal"),
    }
    items = [SaleItemInput("P1", quantity)]
    total = Decimal(price) * quantity - Decimal(discount)
    if second:
        products["P2"] = replace(products["P1"], code="P2", name="Segundo produto")
        items.append(SaleItemInput("P2", 1))
        total += Decimal(price)
    movements = DemoMovementRepository(products, company_max_stock_limit=company_max)
    repo = DemoSaleRepository(products, movements, session=admin)
    row = repo.register_multiple(SimpleNamespace(name="Cliente"), tuple(items), total, discount=Decimal(discount))
    return repo, products, movements, row


def payload(row, quantity=1, index=0):
    return [{"sale_item_id": row["items"][index]["id"], "quantity": quantity}]


@pytest.mark.parametrize("session", [None, SimpleNamespace(
    role="ADMIN", user_id="admin", company_id="company",
)])
def test_constructor_initializes_return_state_with_or_without_session(session):
    repo = DemoSaleRepository({}, session=session)
    assert repo._session is session
    for name in ("_return_sales", "_returns", "_return_requests", "_product_ids"):
        assert getattr(repo, name) == {}
    assert repo.returns == ()


def test_constructor_does_not_share_return_state_between_instances():
    first, second = DemoSaleRepository({}), DemoSaleRepository({})
    for name in ("_return_sales", "_returns", "_return_requests", "_product_ids"):
        first_state, second_state = getattr(first, name), getattr(second, name)
        assert first_state is not second_state
        first_state["only-first"] = "marker"
        assert second_state == {}


def test_legacy_sale_without_session_keeps_seeds_and_publishes_original_snapshot():
    products = {
        "P1": Product("P1", "Produto", "Categoria", "UN", "1.00", "0", True, "10", "Normal"),
    }
    repo = DemoSaleRepository(products)
    seeds = deepcopy(repo.rows)
    sale = repo.register_multiple(
        SimpleNamespace(name="Cliente"), (SaleItemInput("P1", 2),), Decimal("2.00"),
    )
    assert len(repo.rows) == len(seeds) + 1
    assert repo.rows[0] == sale
    assert repo.rows[1:] == seeds
    assert products["P1"].stock == "8"
    item_id = sale["items"][0]["id"]
    snapshot = repo._return_sales[sale["id"]]
    assert snapshot["items"][0].sale_item_id == item_id
    assert snapshot["items"][0].unit_price == Decimal("1.00")
    assert snapshot["items"][0].discount_amount == 0
    assert snapshot["product_ids"][item_id] == repo._product_ids["P1"]
    assert repo.returns == ()
    assert repo._return_requests == {}
    # Registrar pelo contrato legado não libera devoluções sem contexto.
    with pytest.raises(PermissionDeniedError):
        repo.get_returnable_items(sale["id"])


def test_receipt_seeds_keep_items_and_totals_without_fabricated_return_snapshots():
    repo = DemoSaleRepository({})
    assert [row["id"] for row in repo.rows] == ["VND-1001", "VND-1002"]
    for row in repo.rows:
        assert row["status"] == "CONCLUIDA"
        assert row["payment_method"] == "DINHEIRO"
        assert row["seller"]
        assert len(row["items"]) == 1
        assert Decimal(row["items"][0]["final_subtotal"]) == Decimal(row["total"])
        assert Decimal(row["original_total"]) == Decimal(row["total"])
        assert Decimal(row["discount"]) == 0
    assert repo._return_sales == {}


def test_partial_then_total_preserves_history_and_original_sale():
    repo, products, movements, row = setup_sale()
    sale_before = deepcopy(row)
    first = repo.partial_return(row["id"], payload(row), " Defeito ", str(uuid4()))
    assert first["total_amount"] == Decimal("1.00")
    assert first["is_total_return"] is False
    assert products["P1"].stock == "8"
    available, = repo.get_returnable_items(row["id"])
    assert available["quantity_returned"] == 1
    assert available["max_returnable"] == 2
    last = repo.partial_return(row["id"], payload(row, 2), "Restante", str(uuid4()))
    assert last["total_amount"] == Decimal("1.99")
    assert last["is_total_return"] is True
    assert products["P1"].stock == "10"
    assert repo.get_returnable_items(row["id"]) == []
    assert row == sale_before
    assert row["status"] == "CONCLUIDA"
    assert len(repo.returns) == 2
    assert repo.returns[0]["user_id"] == "admin"
    assert repo.returns[0]["reason"] == "Defeito"
    entries = [m for m in movements._movements if m.get("return_id")]
    assert len(entries) == 2
    assert all(m["kind"] == "ENTRADA" and m["status"] == "CONFIRMADA" for m in entries)
    assert entries[0]["return_id"] == first["return_id"]
    assert entries[0]["sale_id"] == row["id"]
    assert entries[0]["sale_item_id"] == row["items"][0]["id"]


def test_price_changes_and_inactivation_do_not_change_original_return_value():
    repo, products, _, row = setup_sale()
    products["P1"] = replace(products["P1"], name="Nome atual", sale_price="999.00", active=False)
    row["items"][0]["unit_price"] = "1234.00"  # Não pode mutilar o snapshot privado.
    item, = repo.get_returnable_items(row["id"])
    assert item["product_name"] == "Produto original"
    assert repo.partial_return(row["id"], payload(row, 3), "Defeito", str(uuid4()))["total_amount"] == Decimal("2.99")
    assert products["P1"].active is False


def test_over_return_does_not_change_any_state():
    repo, products, movements, row = setup_sale()
    repo.partial_return(row["id"], payload(row, 2), "Defeito", str(uuid4()))
    before = deepcopy((products, movements._movements, repo.returns, repo.rows))
    with pytest.raises(ValueError, match="excede"):
        repo.partial_return(row["id"], payload(row, 2), "Defeito", str(uuid4()))
    assert (products, movements._movements, repo.returns, repo.rows) == before


def test_product_deletion_preserves_eligibility_but_prevents_restock():
    repo, products, movements, row = setup_sale()
    del products["P1"]
    assert repo.get_returnable_items(row["id"])[0]["product_id"] is None
    history = deepcopy(movements._movements)
    with pytest.raises(LookupError):
        repo.partial_return(row["id"], payload(row), "Defeito", str(uuid4()))
    assert repo.returns == ()
    assert movements._movements == history


def test_second_item_failure_rolls_back_everything(monkeypatch):
    repo, products, movements, row = setup_sale(second=True)
    before = deepcopy((products, movements._movements, repo.returns, repo.rows))
    apply = movements._aplicar_no_saldo
    calls = []

    def failing_apply(line, sentido):
        calls.append(line)
        apply(line, sentido)
        if len(calls) == 2:
            raise RuntimeError("Falha no segundo item")

    monkeypatch.setattr(movements, "_aplicar_no_saldo", failing_apply)
    items = payload(row) + payload(row, index=1)
    with pytest.raises(RuntimeError, match="segundo item"):
        repo.partial_return(row["id"], items, "Defeito", str(uuid4()))
    assert len(calls) == 2
    assert (products, movements._movements, repo.returns, repo.rows) == before


def test_header_publication_failure_rolls_back_stock_and_history():
    repo, products, movements, row = setup_sale()
    before = deepcopy((products, movements._movements, repo.returns))

    class FailingStore(dict):
        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            raise RuntimeError("Falha na publicação")

    repo._returns = FailingStore()
    with pytest.raises(RuntimeError, match="publicação"):
        repo.partial_return(row["id"], payload(row), "Defeito", str(uuid4()))
    assert (products, movements._movements, repo.returns) == before


def test_simultaneous_returns_cannot_exceed_sold_quantity():
    repo, products, _, row = setup_sale(quantity=1, discount="0")

    def attempt(_):
        try:
            return repo.partial_return(row["id"], payload(row), "Defeito", str(uuid4()))
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(repo.returns) == 1
    assert products["P1"].stock == "10"


@pytest.mark.parametrize("role", ["STOCK", "SELLER", None])
def test_repository_direct_access_also_checks_permission(role):
    repo, _, _, row = setup_sale()
    repo._session.role = role
    with pytest.raises(PermissionDeniedError):
        repo.get_returnable_items(row["id"])
    with pytest.raises(PermissionDeniedError):
        repo.partial_return(row["id"], payload(row), "Defeito", str(uuid4()))
    assert repo.returns == ()


def test_other_company_cannot_access_sale_snapshot():
    repo, _, _, row = setup_sale()
    repo._session.company_id = "other-company"
    with pytest.raises(PermissionDeniedError):
        repo.get_returnable_items(row["id"])
    with pytest.raises(PermissionDeniedError):
        repo.partial_return(row["id"], payload(row), "Defeito", str(uuid4()))


def test_missing_session_is_denied():
    repo = DemoSaleRepository({})
    with pytest.raises(PermissionDeniedError):
        repo.get_returnable_items(str(uuid4()))


def test_legacy_demo_sale_is_not_reconstructed_from_current_price():
    repo, _, _, _ = setup_sale()
    legacy = repo.rows[-1]
    with pytest.raises(ValueError, match="UUID"):
        repo.get_returnable_items(legacy["id"])


def test_unknown_or_nonconcluded_sale_cannot_return():
    repo, _, _, row = setup_sale()
    with pytest.raises(LookupError):
        repo.partial_return(str(uuid4()), payload(row), "Defeito", str(uuid4()))
    repo._return_sales[row["id"]]["status"] = "CANCELADA"
    with pytest.raises(ValueError, match="concluída"):
        repo.partial_return(row["id"], payload(row), "Defeito", str(uuid4()))


def test_maximum_stock_failure_preserves_returnable_quantity():
    repo, products, movements, row = setup_sale(company_max=10)
    products["P1"] = replace(products["P1"], stock="10")
    before = deepcopy((products, movements._movements))
    with pytest.raises(ValueError, match="máximo"):
        repo.partial_return(row["id"], payload(row), "Defeito", str(uuid4()))
    assert (products, movements._movements) == before
    assert repo.returns == ()
    assert repo.get_returnable_items(row["id"])[0]["max_returnable"] == 3


def test_history_is_a_defensive_copy():
    repo, _, _, row = setup_sale()
    repo.partial_return(row["id"], payload(row), "Defeito", str(uuid4()))
    repo.returns[0]["reason"] = "Alterado"
    assert repo.returns[0]["reason"] == "Defeito"


def test_return_movement_cannot_be_cancelled_independently():
    repo, _, movements, row = setup_sale()
    repo.partial_return(row["id"], payload(row), "Defeito", str(uuid4()))
    movement = movements._movements[-1]
    with pytest.raises(ValueError, match="cancelada isoladamente"):
        movements.cancel(movement["id"])


@pytest.mark.parametrize("quantity,requested,discount,expected,is_total", [
    (3, 1, "0.01", "1.00", False),
    (3, 3, "0.01", "2.99", True),
    (1, 1, "1.00", "0.00", True),
])
def test_demo_and_mocked_supabase_share_result_contract(quantity, requested, discount, expected, is_total):
    # Fixture de contrato, NÃO execução da regra em PostgreSQL.
    repo, _, _, row = setup_sale(quantity=quantity, discount=discount)

    class RPC:
        def rpc(self, name, args):
            assert name == "fn_return_partial_sale"
            return SimpleNamespace(execute=lambda: SimpleNamespace(data={
                "return_id": str(uuid4()), "status": "COMPLETED",
                "total_amount": expected, "is_total_return": is_total,
            }))

    arguments = row["id"], payload(row, requested), "Defeito", str(uuid4())
    demo_result = repo.partial_return(*arguments)
    supabase_result = SupabaseSaleRepository(RPC(), "company").partial_return(*arguments)
    assert demo_result.keys() == supabase_result.keys()
    for field in ("status", "total_amount", "is_total_return"):
        assert demo_result[field] == supabase_result[field]


def test_zero_value_sale_can_be_returned_without_division_by_zero():
    repo, products, _, row = setup_sale(price="0.00", discount="0")
    result = repo.partial_return(row["id"], payload(row, 3), "Defeito", str(uuid4()))
    assert result["total_amount"] == Decimal("0.00")
    assert result["is_total_return"] is True
    assert products["P1"].stock == "10"


def test_unrelated_sale_item_is_rejected_without_writes():
    repo, products, movements, row = setup_sale()
    before = deepcopy((products, movements._movements))
    with pytest.raises(ValueError, match="não encontrado"):
        repo.partial_return(row["id"], [{"sale_item_id": str(uuid4()), "quantity": 1}], "Defeito", str(uuid4()))
    assert repo.returns == ()
    assert (products, movements._movements) == before


def test_different_movement_catalog_is_rejected_before_restock():
    repo, products, _, row = setup_sale()
    other_products = dict(products)
    repo.movements = DemoMovementRepository(other_products)
    with pytest.raises(RuntimeError, match="mesmo catálogo"):
        repo.partial_return(row["id"], payload(row), "Defeito", str(uuid4()))
    assert repo.returns == ()
    assert products["P1"].stock == "7"
    assert other_products["P1"].stock == "7"


def test_replay_preserves_original_response_after_other_returns_and_catalog_changes():
    repo, products, movements, row = setup_sale()
    key = str(uuid4())
    first = repo.partial_return(row["id"], payload(row), " Defeito ", key)
    original = dict(first)
    repo.partial_return(row["id"], payload(row, 2), "Restante", str(uuid4()))
    first["total_amount"] = Decimal("999")  # Não expor a resposta armazenada.
    del products["P1"]
    repo._return_sales[row["id"]]["status"] = "CANCELADA"
    before = deepcopy((movements._movements, repo.returns))
    replay = repo.partial_return(row["id"], payload(row), "Defeito", key.upper())
    assert replay == original
    assert replay["is_total_return"] is False  # Snapshot da primeira operação.
    replay["is_total_return"] = True
    assert repo.partial_return(row["id"], payload(row), "Defeito", key) == original
    assert (movements._movements, repo.returns) == before


def test_simultaneous_same_key_creates_only_one_return_and_movement():
    repo, products, movements, row = setup_sale(quantity=1, discount="0")
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(
            lambda _: repo.partial_return(row["id"], payload(row), "Defeito", key), range(16)
        ))
    assert all(result == results[0] for result in results)
    assert len(repo.returns) == 1
    assert len([m for m in movements._movements if m.get("return_id")]) == 1
    assert products["P1"].stock == "10"


@pytest.mark.parametrize("change", ["quantity", "reason", "sale"])
def test_same_key_with_different_content_conflicts_without_changes(change):
    repo, products, movements, row = setup_sale()
    key = str(uuid4())
    repo.partial_return(row["id"], payload(row), "Defeito", key)
    sale_id, items, reason = row["id"], payload(row), "Defeito"
    if change == "quantity":
        items = payload(row, 2)
    elif change == "reason":
        reason = "Outro motivo"
    else:
        other = repo.register_multiple(
            SimpleNamespace(name="Outro cliente"), (SaleItemInput("P1", 1),), Decimal("1.00")
        )
        sale_id, items = other["id"], payload(other)
    before = deepcopy((products, movements._movements, repo.returns, repo._return_requests))
    with pytest.raises(ValueError, match="conteúdo diferente"):
        repo.partial_return(sale_id, items, reason, key)
    assert (products, movements._movements, repo.returns, repo._return_requests) == before


def test_reordered_items_and_extra_fields_replay_without_movements():
    repo, _, movements, row = setup_sale(second=True)
    key = str(uuid4())
    items = payload(row) + payload(row, index=1)
    result = repo.partial_return(row["id"], items, " Defeito ", key)
    before = deepcopy(movements._movements)
    reordered = [
        {**item, "sale_item_id": item["sale_item_id"].upper(), "ignored": True}
        for item in reversed(items)
    ]
    assert repo.partial_return(row["id"], reordered, "Defeito", key.upper()) == result
    assert movements._movements == before


@pytest.mark.parametrize("denial", ["role", "company"])
def test_cached_result_never_bypasses_authorization(denial):
    repo, _, movements, row = setup_sale()
    key = str(uuid4())
    repo.partial_return(row["id"], payload(row), "Defeito", key)
    before = deepcopy((movements._movements, repo.returns))
    if denial == "role":
        repo._session.role = "SELLER"
    else:
        repo._session.company_id = "another-company"
    with pytest.raises(PermissionDeniedError):
        repo.partial_return(row["id"], payload(row), "Defeito", key)
    assert (movements._movements, repo.returns) == before


def test_failed_stock_limit_does_not_reserve_key_and_can_be_retried():
    repo, products, movements, row = setup_sale(company_max=10)
    key = str(uuid4())
    products["P1"] = replace(products["P1"], stock="10")
    before = deepcopy(movements._movements)
    with pytest.raises(ValueError, match="máximo"):
        repo.partial_return(row["id"], payload(row), "Defeito", key)
    assert not repo._return_requests
    assert not repo.returns
    assert movements._movements == before
    products["P1"] = replace(products["P1"], stock="7")
    first = repo.partial_return(row["id"], payload(row), "Defeito", key)
    assert repo.partial_return(row["id"], payload(row), "Defeito", key) == first
    assert products["P1"].stock == "8"


def test_idempotency_publication_failure_rolls_back_everything(monkeypatch):
    repo, products, movements, row = setup_sale()
    key = str(uuid4())
    before = deepcopy((products, movements._movements, repo.returns))

    class FailingStore(dict):
        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            raise RuntimeError("Falha ao publicar idempotência")

    monkeypatch.setattr(repo, "_return_requests", FailingStore())
    with pytest.raises(RuntimeError, match="idempotência"):
        repo.partial_return(row["id"], payload(row), "Defeito", key)
    assert not repo._return_requests
    assert (products, movements._movements, repo.returns) == before
    monkeypatch.setattr(repo, "_return_requests", {})
    repo.partial_return(row["id"], payload(row), "Defeito", key)
    assert len(repo.returns) == 1


@pytest.mark.parametrize("key", [None, "", "invalid", True, 123])
def test_invalid_key_never_changes_demo_state(key):
    repo, products, movements, row = setup_sale()
    before = deepcopy((products, movements._movements, repo.returns))
    with pytest.raises(ValueError, match="UUID"):
        repo.partial_return(row["id"], payload(row), "Defeito", key)
    assert not repo._return_requests
    assert (products, movements._movements, repo.returns) == before


def test_service_recovers_response_lost_after_demo_commit(monkeypatch):
    from stockflow.application.dto.return_dto import CreateReturnDTO, ReturnItemDTO
    from stockflow.application.services.return_service import ReturnService

    repo, products, movements, row = setup_sale(quantity=1, discount="0")
    original = repo.partial_return
    calls = []

    def lose_first_response(sale_id, items, reason, idempotency_key):
        result = original(sale_id, items, reason, idempotency_key)
        calls.append((idempotency_key, dict(result)))
        if len(calls) == 1:
            raise TimeoutError("Resposta perdida depois do commit")
        return result

    monkeypatch.setattr(repo, "partial_return", lose_first_response)
    service = ReturnService(repo, repo._session)
    request = CreateReturnDTO(
        row["id"], [ReturnItemDTO(row["items"][0]["id"], 1)], "Defeito", str(uuid4())
    )
    with pytest.raises(TimeoutError):
        service.create_return(request)
    assert len(calls) == 1  # O serviço não repete automaticamente.
    assert service.create_return(request) == calls[0][1]
    assert calls[0] == calls[1]
    assert len(repo.returns) == 1
    assert len([m for m in movements._movements if m.get("return_id")]) == 1
    assert products["P1"].stock == "10"


def test_idempotency_key_is_scoped_by_company():
    repo, _, _, row = setup_sale()
    key = str(uuid4())
    first = repo.partial_return(row["id"], payload(row), "Defeito", key)
    repo._session.company_id = "another-company"
    other = repo.register_multiple(
        SimpleNamespace(name="Outro cliente"), (SaleItemInput("P1", 1),), Decimal("1.00")
    )
    second = repo.partial_return(other["id"], payload(other), "Defeito", key)
    assert second["return_id"] != first["return_id"]
    assert repo.partial_return(other["id"], payload(other), "Defeito", key) == second
    assert len(repo.returns) == 2
