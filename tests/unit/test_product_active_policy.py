"""US02 - a situação ativa/inativa do produto governa novas operações.

A regra tem um dono só: `stockflow.domain.product_status`. Compras, vendas e
movimentações operacionais consultam a mesma política, pelo mesmo motivo que
`domain.permissions` concentra a regra de papel — duas cópias divergem, e a
cópia esquecida é a que deixa passar o produto inativo.

O histórico NÃO passa por aqui. Operação já registrada guarda o produto que
foi associado no momento em que aconteceu; desativar o cadastro depois não
reescreve o passado.
"""

import pytest

from stockflow.domain.enums.operation_kind import OperationKind
from stockflow.domain.exceptions.inactive_product import InactiveProductError
from stockflow.domain.exceptions.product_not_found import ProductNotFoundError
from stockflow.domain.product_status import (
    ensure_product_selectable,
    is_product_selectable,
    selectable_products,
)
from stockflow.presentation.demo_products import Product


def produto(code="PRD-001", name="Monitor", active=True):
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


# ------------------------------------------------------- is_product_selectable

def test_produto_ativo_pode_ser_selecionado():
    assert is_product_selectable(produto(active=True)) is True


def test_produto_inativo_nao_pode_ser_selecionado():
    assert is_product_selectable(produto(active=False)) is False


def test_produto_ausente_nao_pode_ser_selecionado():
    """Falha fechada: sem produto resolvido não há o que autorizar."""
    assert is_product_selectable(None) is False


def test_produto_sem_campo_active_nao_pode_ser_selecionado():
    """Objeto que não declara situação é tratado como indisponível."""

    class SemStatus:
        code = "PRD-999"

    assert is_product_selectable(SemStatus()) is False


# ---------------------------------------------------- ensure_product_selectable

@pytest.mark.parametrize("operacao", list(OperationKind))
def test_produto_ativo_passa_em_qualquer_operacao(operacao):
    assert ensure_product_selectable(produto(), operacao) is not None


@pytest.mark.parametrize("operacao", list(OperationKind))
def test_produto_inativo_e_recusado_em_qualquer_operacao(operacao):
    with pytest.raises(InactiveProductError) as erro:
        ensure_product_selectable(produto(active=False), operacao)

    assert erro.value.product_code == "PRD-001"
    assert erro.value.operation is operacao


def test_mensagem_de_recusa_nomeia_produto_e_operacao():
    with pytest.raises(InactiveProductError) as erro:
        ensure_product_selectable(
            produto(code="PRD-008", name="Teclado", active=False), OperationKind.VENDA
        )

    mensagem = str(erro.value)
    assert "PRD-008" in mensagem
    assert "Teclado" in mensagem
    assert "inativo" in mensagem.lower()
    assert "venda" in mensagem.lower()


def test_produto_inexistente_nao_e_relatado_como_inativo():
    """Mesma distinção que a tela de Vendas já faz para cliente: não existir
    e estar inativo são causas diferentes, e confundi-las esconde divergência
    entre o catálogo e o módulo que consome."""
    with pytest.raises(ProductNotFoundError) as erro:
        ensure_product_selectable(None, OperationKind.COMPRA, code="PRD-404")

    assert "PRD-404" in str(erro.value)
    assert "inativo" not in str(erro.value).lower()


def test_produto_inexistente_nao_e_capturado_como_inativo():
    """`InactiveProductError` não pode servir de rede para o ausente."""
    with pytest.raises(ProductNotFoundError):
        ensure_product_selectable(None, OperationKind.VENDA, code="PRD-404")


def test_ensure_devolve_o_proprio_produto_para_encadear():
    item = produto()
    assert ensure_product_selectable(item, OperationKind.MOVIMENTACAO) is item


# -------------------------------------------------------- selectable_products

def test_selectable_products_filtra_inativos_preservando_a_ordem():
    catalogo = {
        "PRD-001": produto("PRD-001", "Monitor"),
        "PRD-002": produto("PRD-002", "Teclado", active=False),
        "PRD-003": produto("PRD-003", "Mouse"),
    }

    assert [p.code for p in selectable_products(catalogo)] == ["PRD-001", "PRD-003"]


def test_selectable_products_aceita_sequencia_de_produtos():
    itens = [produto("PRD-001"), produto("PRD-002", active=False)]
    assert [p.code for p in selectable_products(itens)] == ["PRD-001"]


def test_selectable_products_de_catalogo_vazio():
    assert selectable_products({}) == ()


# -------------------------------------------------------------- OperationKind

def test_operacoes_cobertas_pela_us02():
    assert {o.value for o in OperationKind} == {"COMPRA", "VENDA", "MOVIMENTACAO"}


def test_operacao_aceita_texto_em_caixa_qualquer():
    assert OperationKind.from_value("venda") is OperationKind.VENDA


def test_operacao_desconhecida_e_recusada():
    with pytest.raises(ValueError):
        OperationKind.from_value("emprestimo")
