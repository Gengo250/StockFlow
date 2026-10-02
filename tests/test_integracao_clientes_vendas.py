"""Integração tela de Usuários -> tela de Vendas (commit af9fb43)."""

import pytest

from stockflow.presentation.widgets.user_table import DEMO_USERS


@pytest.fixture
def janela(qapp):
    from stockflow.presentation.windows.main_window import MainWindow

    return MainWindow()


def botao_venda(tabela, nome):
    for row, user in enumerate(DEMO_USERS):
        if user[0] == nome:
            return tabela.table.cellWidget(row, 5).layout().itemAt(1).widget()
    raise AssertionError(nome)


def test_botao_de_venda_desabilitado_para_cliente_inativo(qapp):
    from stockflow.presentation.widgets.user_table import UserTable

    tabela = UserTable()
    assert botao_venda(tabela, "Patrícia Lima").isEnabled() is False
    assert botao_venda(tabela, "Ana Ferreira").isEnabled() is True


def test_sinal_venda_requested_carrega_o_nome_do_cliente(qapp):
    from stockflow.presentation.widgets.user_table import UserTable

    tabela = UserTable()
    recebidos = []
    tabela.venda_requested.connect(recebidos.append)
    botao_venda(tabela, "Carlos Mendes").click()
    assert recebidos == ["Carlos Mendes"]


def test_clicar_no_carrinho_abre_vendas_com_o_cliente_selecionado(janela):
    botao_venda(janela.page_widgets["usuarios"].user_table, "Carlos Mendes").click()

    assert janela.pages.currentWidget() is janela.vendas_page
    assert janela.vendas_page.cliente_combo.currentData()["nome"] == "Carlos Mendes"


def test_todo_cliente_ativo_da_tabela_existe_na_base_de_vendas(janela):
    """Qualquer usuário com o botão habilitado precisa ser associável."""
    tabela = janela.page_widgets["usuarios"].user_table
    ativos = [u[0] for u in DEMO_USERS if u[4] == "Ativo"]

    falhas = [
        nome for nome in ativos
        if not janela.vendas_page.selecionar_cliente_externo(nome)
    ]
    assert falhas == [], f"clientes ativos sem associação possível: {falhas}"
