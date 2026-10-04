"""A tela de movimentações, ligada ao resto da janela.

O ciclo que esta tela fecha: o saldo já era a soma das movimentações
confirmadas, mas lançar uma entrada ou saída avulsa só era possível por SQL.

O teste mais importante do arquivo é o da PROPAGAÇÃO. Confirmar atualizava o
catálogo e a tabela de Estoque continuava mostrando o saldo antigo, porque a
reconsulta saía cedo quando não há banco e ninguém redesenhava. Unidade
nenhuma pegaria isso — a falha vive no encaixe entre duas telas.
"""

import pytest
from PySide6.QtWidgets import QMessageBox, QPushButton

from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.pages.movimentacoes import MovimentacoesPage
from stockflow.presentation.windows.main_window import MainWindow


@pytest.fixture
def sem_dialogos(monkeypatch):
    avisos = []
    for nome in ("critical", "warning", "information"):
        monkeypatch.setattr(QMessageBox, nome,
                            staticmethod(lambda *a, _n=nome, **k: avisos.append(_n)))
    return avisos


@pytest.fixture
def janela(qapp, request):
    abertas = []

    def criar(papel=UserRole.ADMIN):
        window = MainWindow(conta_por_papel(papel).session())
        abertas.append(window)
        window.show_page("movimentacoes")
        return window

    request.addfinalizer(lambda: [w.close() for w in abertas])
    return criar


def lancar(window, code="PRD-009", especie=MovementKind.SAIDA, quantidade=5,
           confirmar=False):
    page = window.movimentacoes_page
    page.produto_combo.setCurrentIndex(page.produto_combo.findData(code))
    page.especie_combo.setCurrentIndex(page.especie_combo.findData(especie))
    if especie == MovementKind.ENTRADA:
        page.fornecedor_combo.setCurrentIndex(1)
    page.quantidade_input.setValue(quantidade)
    botao = (page.registrar_confirmar_button if confirmar
             else page.registrar_button)
    botao.click()


def acoes_da_linha(page, linha=0):
    container = page.table.cellWidget(linha, page.table.columnCount() - 1)
    return container.findChildren(QPushButton)


def situacao(page, linha=0):
    return page.table.item(linha, 3).text()


# ================================================ registrar não é confirmar


def test_movimentacao_nasce_pendente_e_nao_mexe_no_saldo(janela):
    """A distinção inteira da US03 em um teste."""
    window = janela()
    antes = window.products["PRD-009"].stock

    lancar(window)

    assert window.movimentacoes_page.table.rowCount() == 1
    assert situacao(window.movimentacoes_page) == "Pendente"
    assert window.products["PRD-009"].stock == antes


def test_confirmar_altera_o_saldo(janela):
    window = janela()
    lancar(window, quantidade=5)             # PRD-009 tem 18

    acoes_da_linha(window.movimentacoes_page)[0].click()

    assert situacao(window.movimentacoes_page) == "Confirmada"
    assert window.products["PRD-009"].stock == "13"


def test_registrar_e_confirmar_faz_os_dois_passos(janela):
    """Atalho para quem lança algo que já aconteceu."""
    window = janela()
    lancar(window, quantidade=3, confirmar=True)

    assert situacao(window.movimentacoes_page) == "Confirmada"
    assert window.products["PRD-009"].stock == "15"


def test_entrada_soma_e_saida_subtrai(janela):
    window = janela()
    lancar(window, especie=MovementKind.ENTRADA, quantidade=7, confirmar=True)
    assert window.products["PRD-009"].stock == "25"

    lancar(window, especie=MovementKind.SAIDA, quantidade=10, confirmar=True)
    assert window.products["PRD-009"].stock == "15"


def test_cancelar_uma_confirmada_devolve_o_saldo(janela):
    window = janela()
    antes = window.products["PRD-009"].stock
    lancar(window, quantidade=5, confirmar=True)
    assert window.products["PRD-009"].stock != antes

    acoes_da_linha(window.movimentacoes_page)[1].click()

    assert situacao(window.movimentacoes_page) == "Cancelada"
    assert window.products["PRD-009"].stock == antes


# ==================================== propagação: o bug que o E2E encontrou


def test_confirmar_atualiza_a_TABELA_DE_ESTOQUE(janela):
    """A regressão real: o catálogo mudava e a tabela mostrava o saldo antigo.

    `_saldo_mudou` reconsultava o banco; sem banco, saía cedo e ninguém
    redesenhava. O catálogo marcava 13 e a tela de Estoque seguia em 18.
    """
    window = janela()
    lancar(window, quantidade=5, confirmar=True)

    window.show_page("estoque")
    estoque = window.estoque_page
    linha = [r for r in range(estoque.table.rowCount())
             if estoque.table.item(r, 0).text() == "PRD-009"][0]

    assert estoque.table.item(linha, 3).text() == "13"


def test_confirmar_tira_o_produto_da_oferta_de_vendas_quando_zera(janela):
    """Vendas também lê o catálogo; zerar o saldo precisa chegar lá."""
    window = janela()
    estoque_inicial = int(window.products["PRD-009"].stock)

    lancar(window, quantidade=estoque_inicial, confirmar=True)

    assert window.products["PRD-009"].stock == "0"
    assert window.products["PRD-009"].stock_status == "Crítico"


# ======================================================== permissão (US05)


@pytest.mark.parametrize("papel", [UserRole.ADMIN, UserRole.STOCK])
def test_papel_autorizado_entra_e_lanca(janela, papel):
    window = janela(papel)

    assert window.pages.currentWidget() is window.movimentacoes_page
    lancar(window)
    assert window.movimentacoes_page.table.rowCount() == 1


def test_vendedor_nao_abre_a_tela(qapp, request, sem_dialogos):
    """`fn_register_movement` recusa o SELLER; nem a consulta é dele."""
    window = MainWindow(conta_por_papel(UserRole.SELLER).session())
    request.addfinalizer(window.close)

    assert window.show_page("movimentacoes") is False
    assert sem_dialogos


def test_vendedor_nao_ve_o_item_no_menu(qapp, request):
    window = MainWindow(conta_por_papel(UserRole.SELLER).session())
    request.addfinalizer(window.close)

    assert not window.sidebar.item_is_visible("movimentacoes")


def test_relogin_para_vendedor_tranca_os_controles(janela):
    """A janela sobrevive ao logout; reexibi-la não pode herdar a permissão."""
    window = janela(UserRole.ADMIN)
    assert window.movimentacoes_page.registrar_button.isEnabled()

    window.apply_session(conta_por_papel(UserRole.SELLER).session())

    assert not window.movimentacoes_page.registrar_button.isEnabled()
    assert not window.sidebar.item_is_visible("movimentacoes")


# ================================================= validação e página isolada


def test_lancar_sem_produto_e_recusado(janela):
    window = janela()
    page = window.movimentacoes_page
    page.produto_combo.setCurrentIndex(0)      # o placeholder

    page.registrar_button.click()

    assert page.table.rowCount() == 0
    assert "produto" in page.warning_label.text().casefold()


def test_a_oferta_tem_so_produtos_ativos(janela):
    """Mesma política da US02: inativo está fora de operação."""
    window = janela()
    page = window.movimentacoes_page
    assert page.produto_combo.findData("PRD-009") >= 0

    window.estoque_page.toggle_product_status(
        next(p for p in window.estoque_page.produtos if p[0] == "PRD-009")
    )
    page.reload_products()

    assert page.produto_combo.findData("PRD-009") < 0


def test_pagina_isolada_nao_precisa_de_sessao_nem_banco(qapp):
    """Mesmo contrato das demais telas: ela pede, a janela faz acontecer."""
    page = MovimentacoesPage()
    try:
        assert page.table.rowCount() == 0
        assert page.list_state_label.isVisibleTo(page)
    finally:
        page.close()


def test_falha_ao_carregar_aparece_na_area_da_lista(qapp):
    page = MovimentacoesPage()
    try:
        page.show_load_error(RuntimeError("timeout"))

        assert page.load_error_label.isVisibleTo(page)
        assert "timeout" in page.load_error_label.text()
        assert not page.table.isVisibleTo(page)
    finally:
        page.close()
