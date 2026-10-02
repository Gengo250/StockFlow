"""Integração: clicar no carrinho em Usuários leva à página de Vendas já associada."""

import pytest

from stockflow.presentation.pages.vendas import VendasPage
from stockflow.presentation.widgets.user_table import DEMO_USERS
from stockflow.presentation.windows.main_window import MainWindow

VENDA_BUTTON_INDEX = 1


@pytest.fixture
def window(qapp):
    return MainWindow()


def users_table(window):
    return window.page_widgets["usuarios"].user_table


def venda_button(window, name):
    row = next(i for i, u in enumerate(DEMO_USERS) if u[0] == name)
    actions = users_table(window).table.cellWidget(row, 5)
    return actions.layout().itemAt(VENDA_BUTTON_INDEX).widget()


def test_pagina_de_vendas_substituiu_o_coming_soon(window):
    assert isinstance(window.page_widgets["vendas"], VendasPage)


def test_clique_navega_para_vendas_e_seleciona_o_cliente(window):
    venda_button(window, "Ana Ferreira").click()

    assert window.pages.currentWidget() is window.vendas_page
    assert window.vendas_page.cliente_combo.currentData()["nome"] == "Ana Ferreira"


def test_fluxo_completo_registra_venda_vinda_da_tela_de_usuarios(window):
    venda_button(window, "Carlos Mendes").click()
    window.vendas_page.val_input.setText("780,00")
    window.vendas_page._registrar_venda()

    assert window.vendas_page.table.item(0, 1).text() == "Carlos Mendes"
    assert window.vendas_page.table.item(0, 2).text() == "R$ 780,00"


def test_usuario_ativo_ausente_da_base_de_clientes_nao_vira_falso_inativo(window):
    """Roberto Souza está Ativo em Usuários mas não existe na base de Vendas."""
    venda_button(window, "Roberto Souza").click()

    aviso = window.vendas_page.warning_label.text()
    assert aviso != "", "deveria haver algum feedback ao usuário"
    assert "inativo" not in aviso.lower(), (
        f"cliente ativo foi reportado como inativo: {aviso!r}"
    )
