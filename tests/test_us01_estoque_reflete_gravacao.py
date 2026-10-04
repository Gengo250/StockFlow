"""US01 - a tela de Estoque reflete o que foi gravado.

A limitação que estes testes fecham: a tabela de Estoque era montada uma
única vez, a partir de uma cópia em tuplas de `DEMO_PRODUCTS`, e nunca mais
era redesenhada. Quem cadastrava ou editava via a mudança em Produtos e na
ficha, mas voltava para o Estoque e encontrava o estado antigo.

O teste do SELLER é o mais importante do arquivo: remontar a tabela recria
os botões de ação, e um botão recém-criado nasce habilitado. Sem reaplicar a
permissão do papel na recarga, um vendedor ganharia editar/excluir ativos nas
linhas novas — regressão de segurança da US01, não detalhe de UI.
"""

import pytest
from PySide6.QtWidgets import QMessageBox, QPushButton

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.presentation.pages.estoque import EstoquePage
from stockflow.presentation.widgets.stock_table import ACTIONS_COLUMN
from stockflow.presentation.windows.main_window import MainWindow

CODE_COLUMN = 0
STOCK_COLUMN = 3
STATUS_COLUMN = 6


def sessao(papel):
    return conta_por_papel(papel).session()


@pytest.fixture
def sem_dialogos(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda *args, **kwargs: chamadas.append(args)),
    )
    return chamadas


@pytest.fixture
def janela(qapp, request):
    abertas = []

    def criar(sessao_do_teste=None):
        window = MainWindow(sessao_do_teste)
        abertas.append(window)
        window.show()
        return window

    request.addfinalizer(lambda: [w.close() for w in abertas])
    return criar


def codigos_na_tabela(page):
    return [
        page.table.item(row, CODE_COLUMN).text()
        for row in range(page.table.rowCount())
    ]


def linha_do_codigo(page, codigo):
    return codigos_na_tabela(page).index(codigo)


def celulas(page, row):
    return [
        page.table.item(row, column).text()
        for column in range(page.table.columnCount() - 1)
    ]


def botoes_de_acao(page):
    """Os botões como estão na tabela, não a lista rastreada pelo widget.

    Ler do `cellWidget` prova que a permissão alcançou os botões que o
    usuário realmente consegue clicar, e não apenas uma lista interna que
    pode ter ficado apontando para widgets já destruídos.
    """
    encontrados = []
    for row in range(page.table.rowCount()):
        container = page.table.cellWidget(row, ACTIONS_COLUMN)
        assert container is not None, f"linha {row} ficou sem botões de ação"
        encontrados.extend(container.findChildren(QPushButton))
    return encontrados


# ------------------------------------------------- cadastro reflete na tabela


def test_estoque_mostra_o_produto_recem_cadastrado(janela, sem_dialogos):
    window = janela(sessao(UserRole.ADMIN))
    linhas_antes = window.estoque_page.table.rowCount()

    window.estoque_page.new_product_button.click()
    page = window.novo_produto_page
    page.name_input.setText("Webcam 4K")
    if page.category_input.findText("Eletrônicos") < 0:
        page.category_input.addItem("Eletrônicos")
    page.category_input.setCurrentText("Eletrônicos")
    page.sale_price_input.setValue(499.0)
    page.initial_stock_input.setValue(30)
    codigo = page.code_input.text()
    page.save_button.click()

    assert window.last_save_error is None
    estoque = window.estoque_page
    assert estoque.table.rowCount() == linhas_antes + 1
    assert codigo in codigos_na_tabela(estoque)
    assert celulas(estoque, linha_do_codigo(estoque, codigo)) == [
        # Cadastro novo nasce SEM mínimo: a US03 o tornou opcional, e o
        # formulário parou de sugerir 10. Sem limiar, a situação é Normal.
        codigo, "Webcam 4K", "Eletrônicos", "30", "—", "R$ 499,00",
        "Normal", "Ativo",
    ]


# --------------------------------------------------- edição reflete na tabela


def test_estoque_mostra_o_novo_valor_depois_da_edicao(janela, sem_dialogos):
    window = janela(sessao(UserRole.ADMIN))
    estoque = window.estoque_page
    assert estoque.table.item(linha_do_codigo(estoque, "PRD-009"),
                              STOCK_COLUMN).text() == "18"

    estoque.stock_table.edit_buttons[0].click()
    page = window.editar_produto_page
    assert page.code_input.text() == "PRD-009"
    page.initial_stock_input.setValue(42)
    page.save_button.click()

    assert window.last_save_error is None
    linha = linha_do_codigo(estoque, "PRD-009")
    assert estoque.table.item(linha, STOCK_COLUMN).text() == "42"
    # 42 contra mínimo 10 -> Normal; a linha inteira vem do catálogo, não só a
    # célula que o formulário tocou.
    assert estoque.table.item(linha, STATUS_COLUMN).text() == "Normal"


# ------------------------------------------- permissão sobrevive à recarga


def test_vendedor_continua_sem_acoes_depois_da_recarga(janela):
    window = janela(sessao(UserRole.SELLER))
    estoque = window.estoque_page
    assert botoes_de_acao(estoque)
    assert not any(b.isEnabled() for b in botoes_de_acao(estoque))

    estoque.reload_products()

    assert botoes_de_acao(estoque), "a recarga não pode deixar linhas sem ações"
    assert not any(b.isEnabled() for b in botoes_de_acao(estoque))
    assert not any(b.isEnabled() for b in estoque.stock_table.action_buttons)
    assert not any(b.isEnabled() for b in estoque.stock_table.edit_buttons)


def test_recarga_nao_deixa_botoes_orfaos_na_lista_rastreada(janela):
    """As listas de botões precisam descrever a tabela atual, não a anterior."""
    window = janela(sessao(UserRole.ADMIN))
    estoque = window.estoque_page

    estoque.reload_products()

    assert len(estoque.stock_table.edit_buttons) == estoque.table.rowCount()
    assert len(estoque.stock_table.action_buttons) == 2 * estoque.table.rowCount()
    assert estoque.stock_table.edit_buttons == [
        estoque.table.cellWidget(row, ACTIONS_COLUMN).findChildren(QPushButton)[0]
        for row in range(estoque.table.rowCount())
    ]


def test_editar_depois_da_recarga_abre_o_produto_da_linha(janela, sem_dialogos):
    """Os botões remontados precisam continuar ligados ao produto certo."""
    window = janela(sessao(UserRole.ADMIN))
    estoque = window.estoque_page

    estoque.reload_products()
    linha = linha_do_codigo(estoque, "PRD-007")
    estoque.stock_table.edit_buttons[linha].click()

    assert window.pages.currentWidget() is window.editar_produto_page
    assert window.editar_produto_page.code_input.text() == "PRD-007"


# ------------------------------------------------- página isolada (sem janela)


def test_pagina_sem_argumento_usa_o_catalogo_de_demonstracao(qapp):
    page = EstoquePage()
    try:
        assert page.table.rowCount() == len(DEMO_PRODUCTS)
        assert codigos_na_tabela(page) == list(DEMO_PRODUCTS)
        assert page.produtos[0][0] == next(iter(DEMO_PRODUCTS))
    finally:
        page.close()


def test_pagina_recebe_catalogo_compartilhado_e_recarrega(qapp):
    catalogo = dict(DEMO_PRODUCTS)
    page = EstoquePage(catalogo)
    try:
        assert codigos_na_tabela(page) == list(catalogo)

        novo = DEMO_PRODUCTS["PRD-007"].__class__(
            "PRD-100", "Webcam 4K", "Eletrônicos", "Unidade (UN)",
            "R$ 499,00", "R$ 300,00", True, "30", "Normal",
        )
        catalogo[novo.code] = novo
        page.reload_products()

        assert "PRD-100" in codigos_na_tabela(page)
        assert page.table.rowCount() == len(catalogo)
    finally:
        page.close()
