"""US02 - o ponto único por onde compras, vendas e movimentações escolhem produto.

A política de domínio responde "este produto pode?". Falta alguém que
resolva o código no catálogo antes de perguntar — e é esse serviço, para que
cada módulo consumidor não repita a dupla "procura no dict, olha o `active`".

O serviço é só leitura: validar uma seleção nunca grava no catálogo.
"""

import pytest

from stockflow.application.services.product_selection_service import (
    ProductSelectionService,
)
from stockflow.domain.enums.operation_kind import OperationKind
from stockflow.domain.exceptions.inactive_product import InactiveProductError
from stockflow.domain.exceptions.product_not_found import ProductNotFoundError
from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.presentation.demo_products import Product


def produto(code, name="Produto", active=True):
    return Product(
        code=code,
        name=name,
        category="Eletrônicos",
        unit="Unidade (UN)",
        sale_price="R$ 10,00",
        cost="R$ 5,00",
        active=active,
        stock="7",
        stock_status="Normal",
    )


@pytest.fixture
def catalogo():
    return {
        "PRD-001": produto("PRD-001", "Monitor"),
        "PRD-002": produto("PRD-002", "Teclado", active=False),
        "PRD-003": produto("PRD-003", "Mouse"),
    }


@pytest.fixture
def service(catalogo):
    return ProductSelectionService(DemoProductRepository(catalogo))


# ---------------------------------------------------------- leitura do catálogo

def test_repositorio_devolve_produto_por_codigo(catalogo):
    repositorio = DemoProductRepository(catalogo)
    assert repositorio.get("PRD-001").name == "Monitor"


def test_repositorio_devolve_none_para_codigo_ausente(catalogo):
    assert DemoProductRepository(catalogo).get("PRD-404") is None


def test_repositorio_lista_o_catalogo_na_ordem_de_cadastro(catalogo):
    repositorio = DemoProductRepository(catalogo)
    assert [p.code for p in repositorio.list_all()] == [
        "PRD-001", "PRD-002", "PRD-003",
    ]


# ------------------------------------------------------------ oferta de escolha

def test_disponiveis_omitem_o_produto_inativo(service):
    assert [p.code for p in service.available_products()] == ["PRD-001", "PRD-003"]


def test_desativar_produto_tira_ele_da_oferta(service, catalogo):
    catalogo["PRD-003"] = produto("PRD-003", "Mouse", active=False)
    assert [p.code for p in service.available_products()] == ["PRD-001"]


def test_reativar_produto_devolve_ele_a_oferta(service, catalogo):
    catalogo["PRD-002"] = produto("PRD-002", "Teclado", active=True)
    assert [p.code for p in service.available_products()] == [
        "PRD-001", "PRD-002", "PRD-003",
    ]


# -------------------------------------------------------- validação da seleção

@pytest.mark.parametrize("operacao", list(OperationKind))
def test_produto_ativo_e_aceito_em_compra_venda_e_movimentacao(service, operacao):
    assert service.ensure_selectable("PRD-001", operacao).name == "Monitor"


@pytest.mark.parametrize("operacao", list(OperationKind))
def test_produto_inativo_e_recusado_em_compra_venda_e_movimentacao(service, operacao):
    with pytest.raises(InactiveProductError) as erro:
        service.ensure_selectable("PRD-002", operacao)

    assert erro.value.product_code == "PRD-002"
    assert erro.value.operation is operacao


def test_codigo_ausente_do_catalogo_e_recusado_como_inexistente(service):
    with pytest.raises(ProductNotFoundError):
        service.ensure_selectable("PRD-404", OperationKind.COMPRA)


def test_operacao_em_texto_e_aceita(service):
    assert service.ensure_selectable("PRD-001", "venda").code == "PRD-001"


def test_operacao_desconhecida_nao_valida_nada(service):
    """Operação fora da US02 é erro de programação, não seleção válida."""
    with pytest.raises(ValueError):
        service.ensure_selectable("PRD-001", "emprestimo")


def test_produto_desativado_depois_passa_a_ser_recusado(service, catalogo):
    """O serviço relê o catálogo compartilhado a cada chamada.

    Guardar a lista de ativos na construção faria a validação responder com
    a foto do catálogo no momento em que a tela abriu — e a tela de Vendas
    fica aberta enquanto o Estoque desativa o produto.
    """
    assert service.ensure_selectable("PRD-001", OperationKind.VENDA)

    catalogo["PRD-001"] = produto("PRD-001", "Monitor", active=False)

    with pytest.raises(InactiveProductError):
        service.ensure_selectable("PRD-001", OperationKind.VENDA)


# --------------------------------------------------------------- somente leitura

def test_validar_selecao_nao_altera_o_catalogo(service, catalogo):
    antes = dict(catalogo)

    service.available_products()
    with pytest.raises(InactiveProductError):
        service.ensure_selectable("PRD-002", OperationKind.VENDA)
    with pytest.raises(ProductNotFoundError):
        service.ensure_selectable("PRD-404", OperationKind.VENDA)

    assert catalogo == antes
