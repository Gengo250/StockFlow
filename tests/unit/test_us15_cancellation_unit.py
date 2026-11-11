"""US15, tarefa 1: perfil, status e justificativa antes de efeitos colaterais.

Não certifica RPC real, concorrência, caixa fechado ou a futura estratégia
de entradas compensatórias. Os testes do Demo exercitam o estado em memória;
o espião do serviço verifica encaminhamento, não autorização no banco.
"""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from stockflow.application.dto.sale_filter import MOTIVO_MAXIMO
from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.application.dto.movement_input import MovementInput
from stockflow.application.services.sale_service import SaleService
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_movement_repository import (
    DemoMovementRepository,
)
from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
from stockflow.presentation.demo_products import Product


def session(role="ADMIN"):
    return SimpleNamespace(role=role, user_id="admin-us15", company_id="company-us15")


class CancellationSpy:
    def __init__(self, error=None):
        self.calls = []
        self.error = error
        self.result = {"sale_id": "sale-us15", "status": "CANCELADA"}

    def cancel(self, sale_id, reason):
        self.calls.append((sale_id, reason))
        if self.error is not None:
            raise self.error
        return self.result

    def get(self, sale_id):
        raise AssertionError("O serviço não deve pré-consultar o status da venda.")


def service_with_spy(error=None):
    repository = CancellationSpy(error)
    return SaleService(repository, clients=None, products=None), repository


@pytest.fixture
def demo_repository():
    products = {
        "P-US15": Product(
            "P-US15", "Produto US15", "Categoria", "UN", "10.00", "0",
            True, "10", "Normal",
        ),
    }
    movements = DemoMovementRepository(products)
    return DemoSaleRepository(products, movements, session=session())


@pytest.fixture
def demo_sale(demo_repository):
    repository = demo_repository
    row = repository.register_multiple(
        SimpleNamespace(name="Cliente US15"),
        (SaleItemInput("P-US15", 2),),
        Decimal("20.00"),
    )
    return repository, row


@pytest.fixture
def pending_sale(demo_repository):
    # Uma pendência não é produzida registrando uma venda concluída e
    # trocando seu status: isso deixaria uma saída de estoque artificial.
    row = {
        "id": str(uuid4()),
        "status": "PENDENTE",
        "total": "20.00",
        "items": [{"product_code": "P-US15", "quantity": 2}],
    }
    demo_repository.rows.append(row)
    return demo_repository, row


def demo_state(repository):
    """Inclui também o histórico/snapshot lido pelo fluxo da US20."""
    return deepcopy((
        repository.rows,
        repository._products,
        repository.movements._movements,
        repository._return_sales,
        repository._returns,
        repository._return_requests,
    ))


def test_admin_forwards_normalized_reason_once_and_preserves_result():
    service, repository = service_with_spy()

    result = service.cancel_sale(session(), "sale-us15", " \tVenda incorreta\n ")

    assert repository.calls == [("sale-us15", "Venda incorreta")]
    assert result is repository.result


@pytest.mark.parametrize("role", ["SELLER", "STOCK", "UNKNOWN", None])
def test_unauthorized_profile_never_calls_repository(role):
    service, repository = service_with_spy()

    with pytest.raises(PermissionDeniedError):
        service.cancel_sale(session(role), "sale-us15", "Venda incorreta")

    assert repository.calls == []


def test_missing_session_never_calls_repository():
    service, repository = service_with_spy()

    with pytest.raises(PermissionDeniedError):
        service.cancel_sale(None, "sale-us15", "Venda incorreta")

    assert repository.calls == []


def test_permission_is_checked_before_invalid_reason():
    service, repository = service_with_spy()

    with pytest.raises(PermissionDeniedError):
        service.cancel_sale(session("SELLER"), "sale-us15", 123)

    assert repository.calls == []


@pytest.mark.parametrize("reason", [None, "", "   ", "\t", "\n", " \t\r\n "])
def test_blank_reason_is_rejected_without_calling_repository(reason):
    service, repository = service_with_spy()

    with pytest.raises(ValueError):
        service.cancel_sale(session(), "sale-us15", reason)

    assert repository.calls == []


@pytest.mark.parametrize("reason", [
    123, 0, True, False, ["motivo"], [], {"motivo": "erro"}, {}, b"erro", b"",
])
def test_non_text_reason_is_rejected_with_controlled_error(reason):
    service, repository = service_with_spy()

    with pytest.raises(ValueError):
        service.cancel_sale(session(), "sale-us15", reason)

    assert repository.calls == []


def test_reason_at_existing_length_limit_is_accepted():
    service, repository = service_with_spy()
    reason = "x" * MOTIVO_MAXIMO

    service.cancel_sale(session(), "sale-us15", reason)

    assert repository.calls == [("sale-us15", reason)]


def test_reason_above_existing_length_limit_never_calls_repository():
    service, repository = service_with_spy()

    with pytest.raises(ValueError):
        service.cancel_sale(session(), "sale-us15", "x" * (MOTIVO_MAXIMO + 1))

    assert repository.calls == []


@pytest.mark.parametrize("error", [
    ValueError("Somente venda concluída pode ser cancelada"),
    PermissionDeniedError("cancelar vendas", "ADMIN"),
    TimeoutError("Resultado da operação desconhecido"),
    RuntimeError("Falha do adaptador"),
])
def test_repository_error_is_preserved_without_retry(error):
    service, repository = service_with_spy(error)

    with pytest.raises(type(error)) as raised:
        service.cancel_sale(session(), "sale-us15", "Venda incorreta")

    assert raised.value is error
    assert repository.calls == [("sale-us15", "Venda incorreta")]


@pytest.mark.parametrize("status", list(SaleStatus))
def test_only_concluded_status_is_reversible(status):
    assert status.reversivel is (status is SaleStatus.CONCLUIDA)


@pytest.mark.parametrize("status", ["CANCELADA", "DEVOLVIDA"])
def test_demo_rejects_terminal_sale_without_changing_state(demo_sale, status):
    repository, row = demo_sale
    row["status"] = status
    before = demo_state(repository)

    with pytest.raises(ValueError):
        repository.cancel(row["id"], "Venda incorreta")

    assert demo_state(repository) == before


@pytest.mark.parametrize("status", [None, "", "UNKNOWN", 123])
def test_demo_rejects_invalid_status_without_changing_state(demo_sale, status):
    repository, row = demo_sale
    row["status"] = status
    before = demo_state(repository)

    with pytest.raises(ValueError):
        repository.cancel(row["id"], "Venda incorreta")

    assert demo_state(repository) == before


def test_demo_rejects_missing_status_without_changing_state(demo_sale):
    repository, row = demo_sale
    del row["status"]
    before = demo_state(repository)

    with pytest.raises(ValueError):
        repository.cancel(row["id"], "Venda incorreta")

    assert demo_state(repository) == before


def test_pending_cancellation_is_rejected_without_stock_changes(pending_sale, monkeypatch):
    repository, row = pending_sale
    before = demo_state(repository)

    def unexpected_reversal(*args, **kwargs):
        raise AssertionError("Pendência não pode chamar a reversão de estoque.")

    monkeypatch.setattr(repository.movements, "reverse_sale", unexpected_reversal)
    service = SaleService(repository, clients=None, products=None)
    with pytest.raises(ValueError, match="concluída"):
        service.cancel_sale(session(), row["id"], "Cliente desistiu")
    assert demo_state(repository) == before


def test_repeated_pending_cancellation_remains_rejected(pending_sale):
    repository, row = pending_sale
    before = demo_state(repository)
    for reason in ("Primeira tentativa", "Segunda tentativa"):
        with pytest.raises(ValueError, match="concluída"):
            repository.cancel(row["id"], reason)
    assert demo_state(repository) == before


@pytest.mark.parametrize("kind", [MovementKind.ENTRADA, MovementKind.SAIDA])
def test_pending_with_confirmed_movement_is_rejected_without_changes(
    pending_sale, monkeypatch, kind,
):
    repository, row = pending_sale
    movement_id = repository.movements.register(
        MovementInput("P-US15", kind, 2, confirm=True)
    )
    repository.movements._linha(movement_id)["sale_id"] = row["id"]
    before = demo_state(repository)

    def unexpected_reversal(*args, **kwargs):
        raise AssertionError("Pendência inconsistente não pode reverter estoque.")

    monkeypatch.setattr(repository.movements, "reverse_sale", unexpected_reversal)
    service = SaleService(repository, clients=None, products=None)

    with pytest.raises(ValueError, match="concluída"):
        service.cancel_sale(session(), row["id"], "Cliente desistiu")

    assert demo_state(repository) == before


@pytest.mark.parametrize("movement_status", ["PENDENTE", "CANCELADA", "OUTRA_VENDA"])
def test_pending_without_linked_confirmed_movement_is_also_rejected(
    pending_sale, movement_status,
):
    repository, row = pending_sale
    movement_id = repository.movements.register(MovementInput(
        "P-US15", MovementKind.SAIDA, 2, confirm=movement_status != "PENDENTE",
    ))
    if movement_status == "CANCELADA":
        repository.movements.cancel(movement_id)
    repository.movements._linha(movement_id)["sale_id"] = (
        str(uuid4()) if movement_status == "OUTRA_VENDA" else row["id"]
    )
    before = demo_state(repository)

    with pytest.raises(ValueError, match="concluída"):
        repository.cancel(row["id"], "Cliente desistiu")

    assert demo_state(repository) == before


def test_pending_sale_cannot_be_returned(pending_sale):
    repository, row = pending_sale
    before = demo_state(repository)

    with pytest.raises(ValueError, match=r"(?i)conclu[ií]da"):
        repository.revert(row["id"], "Devolução indevida")

    assert demo_state(repository) == before


def test_concluded_cancellation_updates_us20_snapshot_and_blocks_new_returns(demo_sale):
    repository, row = demo_sale
    repository.cancel(row["id"], "Venda incorreta")
    assert repository._return_sales[row["id"]]["status"] == "CANCELADA"
    before = demo_state(repository)

    with pytest.raises(ValueError, match=r"(?i)conclu[ií]da"):
        repository.get_returnable_items(row["id"])

    with pytest.raises(ValueError, match=r"(?i)conclu[ií]da"):
        repository.partial_return(
            row["id"], [{"sale_item_id": row["items"][0]["id"], "quantity": 1}],
            "Devolução indevida", str(uuid4()),
        )

    assert demo_state(repository) == before


def test_demo_unknown_sale_is_rejected_without_changing_state(demo_sale):
    repository, _ = demo_sale
    before = demo_state(repository)

    with pytest.raises(ValueError):
        repository.cancel("unknown-sale-us15", "Venda incorreta")

    assert demo_state(repository) == before


def test_invalid_request_through_service_preserves_demo_state(demo_sale):
    repository, row = demo_sale
    service = SaleService(repository, clients=None, products=None)
    before = demo_state(repository)

    with pytest.raises(ValueError):
        service.cancel_sale(session(), row["id"], "\t\n")

    assert demo_state(repository) == before
