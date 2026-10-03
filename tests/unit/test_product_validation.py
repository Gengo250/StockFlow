"""Validações de negócio aplicadas antes de gravar produtos."""

import pytest

from stockflow.application.dto.product_input import ProductInput
from stockflow.application.services.product_service import ProductService
from stockflow.domain.entities.session import Session
from stockflow.domain.enums.user_role import UserRole
from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.presentation.demo_products import DEMO_PRODUCTS


def sessao():
    return Session(
        user_id="u-1",
        name="Administradora",
        email="admin@stockflow.dev",
        role=UserRole.ADMIN,
        company_id="c-1",
    )


def dados(**alteracoes):
    valores = {
        "code": "PRD-100",
        "name": "Webcam 4K",
        "category": "Eletrônicos",
        "unit": "Unidade (UN)",
        "sale_price": "R$ 499,00",
        "cost": "R$ 250,00",
        "stock": "10",
    }
    valores.update(alteracoes)
    return ProductInput(**valores)


def servico(produtos=None, **opcoes):
    catalogo = dict(DEMO_PRODUCTS if produtos is None else produtos)
    repositorio = DemoProductRepository(catalogo, **opcoes)
    return ProductService(repositorio), repositorio, catalogo


def test_dados_validos_criam_produto():
    service, _, catalogo = servico()

    assert service.create_product(sessao(), dados()) == "PRD-100"
    assert catalogo["PRD-100"].name == "Webcam 4K"


def test_repositorio_expõe_somente_categorias_e_unidades_ativas():
    _, repositorio, _ = servico(
        active_categories={"Periféricos"},
        active_units={"Pacote (PCT)"},
    )

    assert repositorio.list_active_categories() == ("Periféricos",)
    assert repositorio.list_active_units() == ("Pacote (PCT)",)


@pytest.mark.parametrize(
    "campo, valor, mensagem",
    [
        ("code", "  ", "Identificador é obrigatório"),
        ("name", "  ", "Nome é obrigatório"),
        ("category", "Selecione uma categoria", "Categoria é obrigatória"),
        ("unit", "", "Unidade é obrigatória"),
        ("sale_price", "", "Preço de venda é obrigatório"),
        ("cost", "", "Custo é obrigatório"),
    ],
)
def test_campos_obrigatorios_impedem_a_gravacao(campo, valor, mensagem):
    service, _, catalogo = servico()
    antes = dict(catalogo)

    with pytest.raises(ValueError, match=mensagem):
        service.create_product(sessao(), dados(**{campo: valor}))

    assert catalogo == antes


@pytest.mark.parametrize(
    "campo, valor, mensagem",
    [
        ("sale_price", "R$ -0,01", "Preço de venda não pode ser negativo"),
        ("cost", "R$ -1,00", "Custo não pode ser negativo"),
        ("stock", "-1", "Estoque não pode ser negativo"),
    ],
)
def test_valores_negativos_impedem_a_gravacao(campo, valor, mensagem):
    service, _, catalogo = servico()
    antes = dict(catalogo)

    with pytest.raises(ValueError, match=mensagem):
        service.create_product(sessao(), dados(**{campo: valor}))

    assert catalogo == antes


@pytest.mark.parametrize(
    "campo, valor, inativos, mensagem",
    [
        (
            "category",
            "Eletrônicos",
            {"active_categories": {"Periféricos"}},
            "categoria.*está inativa",
        ),
        (
            "unit",
            "Unidade (UN)",
            {"active_units": {"Pacote (PCT)"}},
            "unidade.*está inativa",
        ),
    ],
)
def test_categoria_ou_unidade_inativa_impede_gravacao(
    campo, valor, inativos, mensagem
):
    service, _, catalogo = servico(**inativos)
    antes = dict(catalogo)

    with pytest.raises(ValueError, match=mensagem):
        service.create_product(sessao(), dados(**{campo: valor}))

    assert catalogo == antes


def test_editar_sem_alterar_identificador_nao_gera_falsa_duplicidade():
    produto_existente = DEMO_PRODUCTS["PRD-009"]
    service, _, catalogo = servico({"PRD-009": produto_existente})

    assert service.update_product(
        sessao(), "PRD-009", dados(code="PRD-009", name="Monitor atualizado")
    ) == "PRD-009"
    assert catalogo["PRD-009"].name == "Monitor atualizado"


def test_edicao_recusa_identificador_que_pertence_a_outro_produto():
    service, _, catalogo = servico()
    antes = dict(catalogo)

    with pytest.raises(ValueError, match="PRD-008"):
        service.update_product(
            sessao(), "PRD-009", dados(code="PRD-008", name="Monitor atualizado")
        )

    assert catalogo == antes
    assert catalogo["PRD-009"].name == DEMO_PRODUCTS["PRD-009"].name


def test_edicao_valida_categoria_unidade_e_precos_antes_de_atualizar():
    service, _, catalogo = servico(
        active_categories={"Periféricos"},
    )
    antes = catalogo["PRD-009"]

    with pytest.raises(ValueError, match="categoria.*está inativa"):
        service.update_product(
            sessao(), "PRD-009", dados(code="PRD-009", sale_price="R$ 0,00")
        )

    assert catalogo["PRD-009"] == antes


@pytest.mark.parametrize(
    "campo, valor",
    [("sale_price", "valor inválido"), ("cost", "NaN"), ("sale_price", "Infinity")],
)
def test_preco_nao_numerico_ou_nao_finito_e_recusado(campo, valor):
    service, _, catalogo = servico()
    antes = dict(catalogo)

    with pytest.raises(ValueError, match="valor numérico válido"):
        service.create_product(sessao(), dados(**{campo: valor}))

    assert catalogo == antes
