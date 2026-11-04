"""A tela de indicadores: filtro, estados e recusa de acesso (US16)."""

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import QDate

from stockflow.domain.entities.session import Session
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.sales_indicators import (
    LowStockProduct,
    ProductRanking,
    SalesIndicators,
)
from stockflow.presentation.pages.indicadores import IndicadoresPage


def sessao(papel=UserRole.ADMIN):
    return Session("u-1", "Usuário", "u@example.com", papel, company_id="c-1")


def resumo(revenue="0.00", count=0, ticket="0.00", ranking=()):
    return SalesIndicators(
        revenue=Decimal(revenue), sales_count=count,
        average_ticket=Decimal(ticket), ranking=ranking,
    )


class ServicoFalso:
    def __init__(self, comercial=None, baixos=(), erro=None):
        self.comercial = comercial if comercial is not None else resumo()
        self.baixos = baixos
        self.erro = erro
        self.chamadas = []

    def commercial(self, session, date_from=None, date_to=None):
        self.chamadas.append((session, date_from, date_to))
        if self.erro:
            raise self.erro
        return self.comercial

    def low_stock(self, session):
        if self.erro:
            raise self.erro
        return self.baixos


@pytest.fixture
def pagina(qapp):
    paginas = []

    def criar(servico, papel=UserRole.ADMIN):
        page = IndicadoresPage(servico, sessao(papel))
        paginas.append(page)
        # Mostrada de propósito: `isVisible()` responde False para filho de
        # pai não exibido, e os estados de vazio desta tela são justamente
        # widgets que aparecem e somem.
        page.show()
        return page

    yield criar
    for page in paginas:
        page.close()


def periodo(page, inicio, fim):
    page.date_start.setDate(QDate(inicio.year, inicio.month, inicio.day))
    page.date_end.setDate(QDate(fim.year, fim.month, fim.day))


# --------------------------------------------------------- os indicadores


def test_exibe_faturamento_quantidade_e_ticket_medio(pagina):
    page = pagina(ServicoFalso(resumo("1500.00", 3, "500.00")))

    page.refresh()

    assert "1.500,00" in page.metric_values[0].text()
    assert page.metric_values[1].text() == "3"
    assert "500,00" in page.metric_values[2].text()


def test_valores_monetarios_usam_o_formato_da_aplicacao(pagina):
    page = pagina(ServicoFalso(resumo("1234.56", 1, "1234.56")))

    page.refresh()

    assert page.metric_values[0].text() == "R$ 1.234,56"


def test_periodo_sem_dados_mostra_indicadores_zerados(pagina):
    page = pagina(ServicoFalso(resumo()))

    page.refresh()

    assert page.metric_values[0].text() == "R$ 0,00"
    assert page.metric_values[1].text() == "0"
    assert page.metric_values[2].text() == "R$ 0,00"
    assert page.ranking_empty.isVisible()


def test_ranking_aparece_na_ordem_recebida(pagina):
    ranking = (ProductRanking("PRD-2", "Mouse", 7), ProductRanking("PRD-1", "Cabo", 2))
    page = pagina(ServicoFalso(resumo("90.00", 2, "45.00", ranking)))

    page.refresh()

    assert page.ranking_table.rowCount() == 2
    assert page.ranking_table.item(0, 0).text() == "Mouse"
    assert page.ranking_table.item(0, 2).text() == "7"
    assert page.ranking_table.item(1, 0).text() == "Cabo"


def test_estoque_baixo_mostra_produto_saldo_e_minimo(pagina):
    baixos = (LowStockProduct("PRD-1", "Cabo HDMI", 2, 10, "Baixo"),)
    page = pagina(ServicoFalso(baixos=baixos))

    page.refresh()

    assert page.low_stock_table.rowCount() == 1
    linha = [page.low_stock_table.item(0, c).text() for c in range(4)]
    assert linha == ["PRD-1", "Cabo HDMI", "2", "10"]


def test_sem_estoque_baixo_a_lista_avisa_em_vez_de_ficar_vazia(pagina):
    page = pagina(ServicoFalso())

    page.refresh()

    assert page.low_stock_table.rowCount() == 0
    assert page.low_stock_empty.isVisible()


# ------------------------------------------------------------- o filtro


def test_o_periodo_escolhido_vai_para_a_consulta(pagina):
    servico = ServicoFalso()
    page = pagina(servico)
    periodo(page, date(2026, 2, 1), date(2026, 2, 28))

    page.apply_button.click()

    assert servico.chamadas[-1][1:] == (date(2026, 2, 1), date(2026, 2, 28))


def test_a_tela_nasce_com_o_mes_corrente_selecionado(pagina):
    page = pagina(ServicoFalso())
    hoje = date.today()

    assert page.date_start.date().toPython() == hoje.replace(day=1)
    assert page.date_end.date().toPython() == hoje


def test_data_inicial_depois_da_final_avisa_sem_consultar(pagina):
    servico = ServicoFalso()
    page = pagina(servico)
    periodo(page, date(2026, 3, 31), date(2026, 3, 1))

    page.refresh()

    assert page.error.isVisible()
    assert servico.chamadas == []


# ------------------------------------------------------------- estados


def test_mostra_carregando_enquanto_a_consulta_nao_volta(pagina):
    tarefas = []
    page = pagina(ServicoFalso(resumo("10.00", 1, "10.00")))
    page.loader.execute = lambda *tarefa: tarefas.append(tarefa)

    page.refresh()

    assert not page.refresh_button.isEnabled()
    assert "Carregando" in page.summary.text()
    buscar, concluir, _ = tarefas[0]
    concluir(buscar())
    assert page.refresh_button.isEnabled()
    assert "Carregando" not in page.summary.text()


def test_falha_na_consulta_aparece_na_tela_sem_derrubar_a_pagina(pagina):
    page = pagina(ServicoFalso(erro=RuntimeError("rede fora do ar")))

    page.refresh()

    assert page.error.isVisible()
    assert "rede fora do ar" in page.error.text()
    assert page.refresh_button.isEnabled()


def test_falha_apaga_os_indicadores_em_vez_de_manter_o_numero_velho(pagina):
    servico = ServicoFalso(resumo("1500.00", 3, "500.00"))
    page = pagina(servico)
    page.refresh()
    assert "1.500,00" in page.metric_values[0].text()

    servico.erro = RuntimeError("rede fora do ar")
    page.refresh()

    assert page.metric_values[0].text() == "—"


# ------------------------------------------------------------ permissão


def test_perfil_sem_alcada_ve_a_recusa_e_nao_os_numeros(pagina):
    servico = ServicoFalso(erro=PermissionDeniedError("consultar os indicadores",
                                                      UserRole.SELLER))
    page = pagina(servico, papel=UserRole.SELLER)

    page.refresh()

    assert page.error.isVisible()
    assert page.metric_values[0].text() == "—"


# -------------------------------------------------------- integração

@pytest.fixture
def janela(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from stockflow.presentation.windows.main_window import MainWindow

    abertas = []

    def criar(session):
        window = MainWindow(session)
        abertas.append(window)
        return window

    yield criar
    for window in abertas:
        window.close()


def ano_inteiro(page):
    page.date_start.setDate(QDate(2026, 1, 1))
    page.date_end.setDate(QDate(2026, 12, 31))


def test_a_tela_esta_na_navegacao_e_abre_ja_consultada(janela):
    from stockflow.presentation.demo_accounts import conta_admin

    window = janela(conta_admin().session())

    assert window.show_page("indicadores") is True
    assert window.pages.currentWidget() is window.page_widgets["indicadores"]
    assert window.indicadores_page.metric_values[1].text() != "—"


def test_o_item_de_menu_existe_para_o_administrador(janela):
    from stockflow.presentation.demo_accounts import conta_admin

    window = janela(conta_admin().session())
    window.show()

    assert window.sidebar.buttons["indicadores"].isVisible()


@pytest.mark.parametrize("papel", [UserRole.STOCK, UserRole.SELLER])
def test_perfil_sem_alcada_nao_abre_nem_ve_o_item(janela, monkeypatch, papel):
    from PySide6.QtWidgets import QMessageBox
    from stockflow.presentation.demo_accounts import conta_por_papel

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    window = janela(conta_por_papel(papel).session())
    window.show()

    assert window.show_page("indicadores") is False
    assert not window.sidebar.buttons["indicadores"].isVisible()


def test_venda_cancelada_sai_do_faturamento_ponta_a_ponta(janela):
    """US15 e US16 juntas, sem lógica duplicada entre elas.

    O cancelamento continua sendo da US15; aqui só se prova que o indicador
    enxerga o estado que ela gravou.
    """
    from stockflow.presentation.demo_accounts import conta_admin

    session = conta_admin().session()
    window = janela(session)
    window.show_page("indicadores")
    page = window.indicadores_page
    ano_inteiro(page)
    page.refresh()
    antes = page.metric_values[0].text()
    vendas_antes = int(page.metric_values[1].text())

    window.sale_service.cancel_sale(session, "VND-1001", "teste de indicadores")
    page.refresh()

    assert int(page.metric_values[1].text()) == vendas_antes - 1
    assert page.metric_values[0].text() != antes


def test_recebimento_confirmado_tira_o_produto_do_estoque_baixo(janela):
    """US21 e US16 juntas: o indicador lê o saldo, não uma lista própria.

    A entrada confirmada é da história de movimentação/recebimento; aqui só
    se prova que o estoque baixo reflete o saldo que ela gravou, sem
    recalcular nada por conta própria.
    """
    from stockflow.application.dto.movement_input import MovementInput
    from stockflow.domain.enums.movement_kind import MovementKind
    from stockflow.presentation.demo_accounts import conta_admin

    session = conta_admin().session()
    window = janela(session)
    window.show_page("indicadores")
    page = window.indicadores_page
    codigos = lambda: {page.low_stock_table.item(i, 0).text()
                       for i in range(page.low_stock_table.rowCount())}
    assert "PRD-008" in codigos()

    movimento = window.movement_service.register(session, MovementInput(
        product_code="PRD-008", kind=MovementKind.ENTRADA, quantity=50,
        note="recebimento de compra",
    ))
    window.movement_service.confirm(session, movimento)
    page.refresh()

    assert "PRD-008" not in codigos()
