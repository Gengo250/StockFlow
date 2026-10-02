"""US: botão 'associar a uma venda' na tabela de usuários (commit af9fb43)."""

import pytest
from PySide6.QtWidgets import QPushButton

from stockflow.presentation.widgets.user_table import DEMO_USERS, UserTable

VENDA_BUTTON_INDEX = 1  # ordem no layout de ações: editar, venda, toggle


@pytest.fixture
def table(qapp):
    return UserTable()


def venda_button(table, row) -> QPushButton:
    actions = table.table.cellWidget(row, 5)
    return actions.layout().itemAt(VENDA_BUTTON_INDEX).widget()


def row_of(name):
    return next(i for i, u in enumerate(DEMO_USERS) if u[0] == name)


def test_existe_botao_de_venda_em_todas_as_linhas(table):
    for row in range(len(DEMO_USERS)):
        assert isinstance(venda_button(table, row), QPushButton)


@pytest.mark.parametrize("name,status", [(u[0], u[4]) for u in DEMO_USERS])
def test_botao_habilitado_somente_para_ativos(table, name, status):
    button = venda_button(table, row_of(name))
    assert button.isEnabled() is (status == "Ativo")


def test_tooltip_reflete_status(table):
    assert venda_button(table, row_of("Ana Ferreira")).toolTip() == "Associar a uma venda"
    assert "inativo" in venda_button(table, row_of("Patrícia Lima")).toolTip().lower()


def test_clique_emite_venda_requested_com_nome(table, signal_spy):
    received = signal_spy(table.venda_requested)
    venda_button(table, row_of("Carlos Mendes")).click()
    assert received == [("Carlos Mendes",)]


def test_clique_em_inativo_nao_emite(table, signal_spy):
    received = signal_spy(table.venda_requested)
    venda_button(table, row_of("Patrícia Lima")).click()
    assert received == []
