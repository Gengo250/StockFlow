"""Testes de unidade e regressão para US09, US10 e integração fiscal via NFeClient."""

import json
import subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from stockflow.application.dto.movement_input import MovementInput
from stockflow.application.dto.product_input import ProductInput
from stockflow.application.services.movement_service import MovementService
from stockflow.application.services.product_service import ProductService
from stockflow.application.services.sale_service import SaleService
from stockflow.domain.entities.client import Client
from stockflow.domain.entities.session import Session
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.fiscal.nfe_client import NFeClient
from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.infrastructure.repositories.demo_movement_repository import (
    DemoMovementRepository,
)


# ---------------------------------------------------------------------------
# FIXTURES E SESSÕES POR PAPEL
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_session():
    return Session(
        user_id="user-admin",
        name="Admin",
        email="admin@test.com",
        role=UserRole.ADMIN,
        company_id="comp-1",
    )


@pytest.fixture
def stock_session():
    return Session(
        user_id="user-stock",
        name="Stock",
        email="stock@test.com",
        role=UserRole.STOCK,
        company_id="comp-1",
    )


@pytest.fixture
def seller_session():
    return Session(
        user_id="user-seller",
        name="Seller",
        email="seller@test.com",
        role=UserRole.SELLER,
        company_id="comp-1",
    )


@pytest.fixture
def mock_products_repo():
    p = ProductInput(
        code="PRD-001",
        name="Mouse Gamer",
        category="Periféricos",
        unit="Unidade (UN)",
        sale_price="150.00",
        cost="80.00",
        stock="20",
        active=True,
    )
    repo = DemoProductRepository({})
    repo.create(p)
    return repo


@pytest.fixture
def mock_movement_repo(mock_products_repo):
    return DemoMovementRepository(mock_products_repo._products)


# ===========================================================================
# 1. TESTES US10: ENTRADA E SAÍDA DE ESTOQUE + EXCEÇÕES
# ===========================================================================


def test_us10_register_stock_entry_success(
    stock_session, mock_movement_repo, mock_products_repo
):
    service = MovementService(
        repository=mock_movement_repo, product_repository=mock_products_repo
    )
    mov_input = MovementInput(
        product_code="PRD-001",
        kind=MovementKind.ENTRADA,
        quantity=10,
        note="Entrada por nota fiscal",
        confirm=True,
    )
    mov_id = service.register(stock_session, mov_input)
    assert mov_id is not None
    assert int(mock_products_repo.get("PRD-001").stock) == 30


@pytest.mark.parametrize("invalid_qty", [0, -1, -50, "zero", ""])
def test_us10_stock_entry_rejects_non_positive_quantity(
    stock_session, mock_movement_repo, mock_products_repo, invalid_qty
):
    service = MovementService(
        repository=mock_movement_repo, product_repository=mock_products_repo
    )
    mov_input = MovementInput(
        product_code="PRD-001",
        kind=MovementKind.ENTRADA,
        quantity=invalid_qty,
        confirm=False,
    )
    with pytest.raises(ValueError, match="A quantidade deve ser maior que zero"):
        service.register(stock_session, mov_input)


def test_us10_stock_entry_permission_denied_for_seller(
    seller_session, mock_movement_repo, mock_products_repo
):
    service = MovementService(
        repository=mock_movement_repo, product_repository=mock_products_repo
    )
    mov_input = MovementInput(
        product_code="PRD-001", kind=MovementKind.ENTRADA, quantity=5
    )
    with pytest.raises(PermissionDeniedError):
        service.register(seller_session, mov_input)


def test_us10_stock_entry_unregistered_product_fails(
    stock_session, mock_movement_repo, mock_products_repo
):
    service = MovementService(
        repository=mock_movement_repo, product_repository=mock_products_repo
    )
    mov_input = MovementInput(
        product_code="SKU-NAO-EXISTE", kind=MovementKind.ENTRADA, quantity=5
    )
    with pytest.raises((ValueError, LookupError)):
        service.register(stock_session, mov_input)


def test_us10_stock_entry_inactive_product_fails(
    stock_session, mock_movement_repo, mock_products_repo
):
    mock_products_repo.set_active("PRD-001", False)
    service = MovementService(
        repository=mock_movement_repo, product_repository=mock_products_repo
    )
    mov_input = MovementInput(
        product_code="PRD-001", kind=MovementKind.ENTRADA, quantity=5
    )
    with pytest.raises(ValueError, match="Selecione um produto ativo"):
        service.register(stock_session, mov_input)


# ===========================================================================
# 2. TESTES US09: PREÇOS, VALIDAÇÕES E EXCEÇÕES
# ===========================================================================


def test_us09_update_product_price_success(admin_session, mock_products_repo):
    service = ProductService(repository=mock_products_repo)
    atual = mock_products_repo.get("PRD-001")
    novo = ProductInput(
        code=atual.code,
        name=atual.name,
        category=atual.category,
        unit=atual.unit,  # ou "Unidade (UN)"
        sale_price="R$ 199,90",
        cost="R$ 95,00",
        stock=atual.stock,
        active=atual.active,
    )
    code = service.update_product(admin_session, "PRD-001", novo)
    assert code == "PRD-001"
    assert mock_products_repo.get("PRD-001").sale_price == "R$ 199,90"


@pytest.mark.parametrize("invalid_price", ["-10.00", "-0.01", "R$ -50,00"])
def test_us09_rejects_negative_sale_price(
    admin_session, mock_products_repo, invalid_price
):
    service = ProductService(repository=mock_products_repo)
    atual = mock_products_repo.get("PRD-001")
    novo = ProductInput(
        code=atual.code,
        name=atual.name,
        category=atual.category,
        unit=atual.unit,
        sale_price=invalid_price,
        cost="50.00",
        stock=atual.stock,
    )
    with pytest.raises(ValueError, match="não pode ser negativo"):
        service.update_product(admin_session, "PRD-001", novo)


@pytest.mark.parametrize("invalid_cost", ["-1.00", "-100.00", "R$ -2,00"])
def test_us09_rejects_negative_cost(admin_session, mock_products_repo, invalid_cost):
    service = ProductService(repository=mock_products_repo)
    atual = mock_products_repo.get("PRD-001")
    novo = ProductInput(
        code=atual.code,
        name=atual.name,
        category=atual.category,
        unit=atual.unit,
        sale_price="100.00",
        cost=invalid_cost,
        stock=atual.stock,
    )
    with pytest.raises(ValueError, match="não pode ser negativo"):
        service.update_product(admin_session, "PRD-001", novo)


def test_us09_update_product_price_unauthorized_for_seller(
    seller_session, mock_products_repo
):
    service = ProductService(repository=mock_products_repo)
    atual = mock_products_repo.get("PRD-001")
    novo = ProductInput(
        code=atual.code,
        name=atual.name,
        category=atual.category,
        unit=atual.unit,
        sale_price="180.00",
        cost=atual.cost,
        stock=atual.stock,
    )
    with pytest.raises(PermissionDeniedError):
        service.update_product(seller_session, "PRD-001", novo)


def test_us09_update_price_non_existent_product_fails(
    admin_session, mock_products_repo
):
    service = ProductService(repository=mock_products_repo)
    novo = ProductInput(
        code="INEXISTENTE",
        name="Teste",
        category="Periféricos",
        unit="UN",
        sale_price="100.00",
        cost="50.00",
        stock="10",
    )
    with pytest.raises(LookupError, match="não encontrado"):
        service.update_product(admin_session, "INEXISTENTE", novo)


# ===========================================================================
# 3. TESTES FISCAIS: NFeClient, SUBPROCESSO CLI E TRATAMENTO DE FALHAS
# ===========================================================================


def test_nfe_client_success():
    fake_output = json.dumps(
        {
            "status": "AUTORIZADA",
            "chave_acesso": "35261012345678000195650010000000101123456789",
            "protocolo": "PRC-12345",
        }
    )
    client = NFeClient(script_path=Path("/tmp/fake_cli.php"))

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(
            returncode=0, stdout=fake_output, stderr=""
        )
        resposta = client.emitir_nota("VENDA", {"sale_id": "v-1", "total": 150.00})

    assert resposta["status"] == "AUTORIZADA"
    assert "chave_acesso" in resposta


def test_nfe_client_handles_php_script_failure():
    client = NFeClient(script_path=Path("/tmp/fake_cli.php"))

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(
            returncode=1, stdout="", stderr="PHP Fatal error: Certificate expired"
        )
        resposta = client.emitir_nota("MOVIMENTACAO_ESTOQUE", {"movement_id": "m-1"})

    assert resposta["status"] == "REJEITADA"
    assert "Certificate expired" in resposta["erro"]


def test_nfe_client_handles_php_not_installed_exception():
    client = NFeClient(script_path=Path("/tmp/fake_cli.php"))

    with patch("subprocess.run", side_effect=FileNotFoundError("No such file: 'php'")):
        resposta = client.emitir_nota("ALTERACAO_PRECO", {"product_code": "PRD-001"})

    assert resposta["status"] == "ERRO_SISTEMA"
    assert "PHP não instalado" in resposta["mensagem"]


def test_nfe_client_handles_unexpected_exception():
    client = NFeClient(script_path=Path("/tmp/fake_cli.php"))

    with patch("subprocess.run", side_effect=RuntimeError("Memória esgotada no host")):
        resposta = client.emitir_nota("VENDA", {"sale_id": "v-1"})

    assert resposta["status"] == "ERRO_INESPERADO"
    assert "Memória esgotada" in resposta["mensagem"]
