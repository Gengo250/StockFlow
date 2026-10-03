"""US01 - só ADMIN e STOCK cadastram/editam produtos.

Espelha a regra do banco em `database/code/procedures/05_catalog.sql`:
`fn_has_role(company_id, ARRAY['ADMIN','STOCK'])`. Se a lista daqui divergir
da lista do SQL, a UI libera um botão que o banco vai recusar depois.
"""

import pytest

from stockflow.application.dto.product_input import ProductInput
from stockflow.application.services.product_service import ProductService
from stockflow.domain.entities.session import Session
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.permissions import (
    PRODUCT_WRITE_ROLES,
    can_manage_products,
    ensure_can_manage_products,
)


class RepositorioEspiao:
    """Repositório em memória que grava toda chamada recebida.

    O critério de aceite exige provar que nada foi tocado quando a permissão
    é negada, então até `exists()` precisa ficar registrado.
    """

    def __init__(self, produtos=None):
        self.produtos = dict(produtos or {})
        self.chamadas = []

    def exists(self, code):
        self.chamadas.append(("exists", code))
        return code in self.produtos

    def create(self, data):
        self.chamadas.append(("create", data))
        self.produtos[data.code] = data
        return data.code

    def update(self, code, data):
        self.chamadas.append(("update", code, data))
        self.produtos[code] = data
        return data.code


def sessao(role, user_id="u-1"):
    return Session(
        user_id=user_id,
        name="Usuário de Teste",
        email="teste@stockflow.dev",
        role=role,
        company_id="c-1",
    )


def produto(code="PRD-010", name="Headset USB"):
    return ProductInput(
        code=code,
        name=name,
        category="Periféricos",
        unit="Unidade (UN)",
        sale_price="R$ 299,90",
        cost="R$ 150,00",
        stock="12",
    )


# -------------------------------------------------- política de permissão

def test_papeis_de_escrita_batem_com_o_array_do_sql():
    assert PRODUCT_WRITE_ROLES == frozenset({UserRole.ADMIN, UserRole.STOCK})


@pytest.mark.parametrize(
    "role, esperado",
    [(UserRole.ADMIN, True), (UserRole.STOCK, True), (UserRole.SELLER, False)],
)
def test_can_manage_products_cobre_os_tres_papeis(role, esperado):
    assert can_manage_products(role) is esperado
    assert can_manage_products(sessao(role)) is esperado
    assert sessao(role).can_manage_products is esperado


def test_can_manage_products_nega_sessao_ausente():
    assert can_manage_products(None) is False


def test_ensure_nega_sessao_ausente():
    # Sessão ausente é usuário não autenticado: negar, nunca "falhar aberto".
    with pytest.raises(PermissionDeniedError):
        ensure_can_manage_products(None, action="cadastrar produto")


def test_excecao_expoe_acao_e_papel_na_mensagem():
    erro = PermissionDeniedError("cadastrar produto", UserRole.SELLER)
    assert erro.action == "cadastrar produto"
    assert erro.role == UserRole.SELLER
    assert "cadastrar produto" in str(erro)
    assert "SELLER" in str(erro)


# -------------------------------------------------------------- UserRole

@pytest.mark.parametrize("valor", ["admin", "ADMIN", " Admin ", UserRole.ADMIN])
def test_from_value_aceita_texto_e_enum(valor):
    assert UserRole.from_value(valor) is UserRole.ADMIN


@pytest.mark.parametrize("lixo", ["", "GERENTE", None, 42])
def test_from_value_rejeita_valor_desconhecido(lixo):
    with pytest.raises(ValueError):
        UserRole.from_value(lixo)


# --------------------------------------------------------- caminho feliz

@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.STOCK])
def test_admin_e_stock_criam_produto(role):
    repo = RepositorioEspiao()
    service = ProductService(repo)
    dados = produto()

    assert service.create_product(sessao(role), dados) == "PRD-010"
    assert repo.produtos["PRD-010"] == dados
    assert ("create", dados) in repo.chamadas


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.STOCK])
def test_admin_e_stock_editam_produto(role):
    antigo = produto()
    repo = RepositorioEspiao({"PRD-010": antigo})
    service = ProductService(repo)
    novo = produto(name="Headset USB Pro")

    assert service.update_product(sessao(role), "PRD-010", novo) == "PRD-010"
    assert repo.produtos["PRD-010"] == novo
    assert ("update", "PRD-010", novo) in repo.chamadas


# ------------------------------------------------------------- negativas

def test_seller_nao_cria_e_nao_toca_no_repositorio():
    existente = produto("PRD-009", "Monitor")
    repo = RepositorioEspiao({"PRD-009": existente})
    service = ProductService(repo)
    antes = dict(repo.produtos)

    with pytest.raises(PermissionDeniedError) as exc:
        service.create_product(sessao(UserRole.SELLER), produto())

    assert exc.value.role == UserRole.SELLER
    assert repo.chamadas == []
    assert repo.produtos == antes


def test_seller_nao_edita_e_nao_toca_no_repositorio():
    existente = produto("PRD-009", "Monitor")
    repo = RepositorioEspiao({"PRD-009": existente})
    service = ProductService(repo)
    antes = dict(repo.produtos)

    with pytest.raises(PermissionDeniedError):
        service.update_product(
            sessao(UserRole.SELLER), "PRD-009", produto("PRD-009", "Monitor 4K")
        )

    assert repo.chamadas == []
    assert repo.produtos == antes


@pytest.mark.parametrize("operacao", ["create", "update"])
def test_sessao_ausente_e_negada_sem_chamadas(operacao):
    repo = RepositorioEspiao({"PRD-009": produto("PRD-009", "Monitor")})
    service = ProductService(repo)

    with pytest.raises(PermissionDeniedError):
        if operacao == "create":
            service.create_product(None, produto())
        else:
            service.update_product(None, "PRD-009", produto("PRD-009"))

    assert repo.chamadas == []


# --------------------------------------- validação de negócio pós-permissão

def test_create_recusa_codigo_duplicado():
    # Garante que a checagem de permissão não "engoliu" a regra de negócio.
    repo = RepositorioEspiao({"PRD-010": produto()})
    service = ProductService(repo)

    with pytest.raises(ValueError, match="PRD-010"):
        service.create_product(sessao(UserRole.ADMIN), produto())

    assert repo.chamadas == [("exists", "PRD-010")]


def test_update_recusa_codigo_inexistente():
    repo = RepositorioEspiao()
    service = ProductService(repo)

    with pytest.raises(LookupError, match="PRD-404"):
        service.update_product(sessao(UserRole.ADMIN), "PRD-404", produto("PRD-404"))

    assert repo.chamadas == [("exists", "PRD-404")]
