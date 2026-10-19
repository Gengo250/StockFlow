"""Testes da consulta paginada do histórico de movimentações e seus filtros.

Cobre a navegação entre páginas, filtros (produto, espécie, período),
preservação de filtros em recargas e estados vazios.
"""

from datetime import date, timedelta
import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QMessageBox, QPushButton

from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.movement_status import MovementStatus
from stockflow.presentation.demo_products import Product
from stockflow.presentation.pages.movimentacoes import (
    ACTIONS_COLUMN,
    PAGE_SIZE,
    MovimentacoesPage,
)


def _criar_movimento(
    mov_id: str,
    code: str = "PRD-001",
    name: str = "Teclado Mecânico",
    kind: MovementKind = MovementKind.ENTRADA,
    qty: int = 10,
    status: MovementStatus = MovementStatus.CONFIRMADA,
    note: str = "",
    when: str = "Hoje, 10:00",
    supplier: str = "Fornecedor Alpha",
    reason: str = "—",
) -> tuple:
    return (
        mov_id,
        code,
        name,
        kind.value,
        qty,
        status.label,
        note or "—",
        when,
        supplier or "—",
        reason or "—",
    )


@pytest.fixture
def sem_dialogos(monkeypatch):
    """Diálogo modal em teste offscreen trava a suíte: ninguém o fecha.

    Mesma proteção que os demais testes de `MainWindow` usam. Sem ela, uma
    falha inesperada no registro vira execução pendurada em vez de teste
    vermelho — e no CI isso custa o job inteiro.
    """
    avisos = []
    for nome in ("critical", "warning", "information"):
        monkeypatch.setattr(QMessageBox, nome,
                            staticmethod(lambda *a, _n=nome, **k: avisos.append(_n)))
    return avisos


@pytest.fixture
def catalogo():
    return {
        "PRD-001": Product("PRD-001", "Teclado Mecânico", "Periféricos", "UN", "150,00", "80,00", True, "25", "Normal"),
        "PRD-002": Product("PRD-002", "Mouse Gamer", "Periféricos", "UN", "90,00", "45,00", True, "15", "Normal"),
    }


def test_historico_vazio(qapp, catalogo):
    """Sem movimentações: 0 registros, 1 página, controles desabilitados."""
    page = MovimentacoesPage(catalogo)
    page.set_movements(())

    assert page.table.rowCount() == 0
    assert "Página 1 de 1" in page.paginacao_label.text()
    assert "0 registro(s)" in page.paginacao_label.text()
    assert not page.anterior_button.isEnabled()
    assert not page.proximo_button.isEnabled()
    assert page.list_state_label.isVisibleTo(page)


def test_historico_exatamente_uma_pagina(qapp, catalogo):
    """Com 50 itens (PAGE_SIZE), exibe 50 linhas em 1 única página."""
    movs = tuple(_criar_movimento(f"MOV-{i:03d}") for i in range(PAGE_SIZE))
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)

    assert page.table.rowCount() == PAGE_SIZE
    assert "Página 1 de 1" in page.paginacao_label.text()
    assert f"{PAGE_SIZE} registro(s)" in page.paginacao_label.text()
    assert not page.anterior_button.isEnabled()
    assert not page.proximo_button.isEnabled()


def test_paginacao_duas_paginas_avancar_e_voltar(qapp, catalogo):
    """Com 51 itens, gera 2 páginas: página 1 tem 50, página 2 tem 1."""
    movs = tuple(_criar_movimento(f"MOV-{i:03d}") for i in range(PAGE_SIZE + 1))
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)

    # Página 1
    assert page.table.rowCount() == PAGE_SIZE
    assert "Página 1 de 2" in page.paginacao_label.text()
    assert not page.anterior_button.isEnabled()
    assert page.proximo_button.isEnabled()

    # Avança para a página 2
    page.proximo_button.click()
    assert page.table.rowCount() == 1
    assert "Página 2 de 2" in page.paginacao_label.text()
    assert page.anterior_button.isEnabled()
    assert not page.proximo_button.isEnabled()

    # Retorna para a página 1
    page.anterior_button.click()
    assert page.table.rowCount() == PAGE_SIZE
    assert "Página 1 de 2" in page.paginacao_label.text()
    assert not page.anterior_button.isEnabled()
    assert page.proximo_button.isEnabled()


def test_filtro_por_produto(qapp, catalogo):
    """Filtrar por produto específico exibe apenas linhas daquele produto."""
    movs = (
        _criar_movimento("MOV-001", code="PRD-001"),
        _criar_movimento("MOV-002", code="PRD-002"),
        _criar_movimento("MOV-003", code="PRD-001"),
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)
    assert page.table.rowCount() == 3

    # Seleciona PRD-001
    idx = page.filtro_produto_combo.findData("PRD-001")
    assert idx >= 0
    page.filtro_produto_combo.setCurrentIndex(idx)

    assert page.table.rowCount() == 2
    assert "2 registro(s)" in page.paginacao_label.text()
    for row in range(page.table.rowCount()):
        assert "PRD-001" in page.table.item(row, 0).text()


def test_filtro_por_especie(qapp, catalogo):
    """Filtrar por espécie (ENTRADA/SAIDA) retém apenas as correspondentes."""
    movs = (
        _criar_movimento("MOV-001", kind=MovementKind.ENTRADA),
        _criar_movimento("MOV-002", kind=MovementKind.SAIDA),
        _criar_movimento("MOV-003", kind=MovementKind.ENTRADA),
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)

    # Filtra por SAIDA
    idx = page.filtro_especie_combo.findData(MovementKind.SAIDA.value)
    page.filtro_especie_combo.setCurrentIndex(idx)

    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == MovementKind.SAIDA.value


def test_filtro_por_periodo(qapp, catalogo):
    """Filtra por data de início e fim."""
    hoje = date.today()
    ontem = hoje - timedelta(days=1)
    antiga = hoje - timedelta(days=10)

    movs = (
        _criar_movimento("MOV-001", when=hoje.strftime("%d/%m/%Y")),
        _criar_movimento("MOV-002", when=ontem.strftime("%d/%m/%Y")),
        _criar_movimento("MOV-003", when=antiga.strftime("%d/%m/%Y")),
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)

    # Abre o intervalo em ontem: a antiga sai, hoje e ontem ficam.
    page.filtro_data_inicio.setDate(QDate(ontem.year, ontem.month, ontem.day))
    assert page.table.rowCount() == 2
    assert "2 registro(s)" in page.paginacao_label.text()

    # Fecha o intervalo em ontem. Repare que o valor PRECISA mudar: os dois
    # QDateEdit nascem com a data de hoje, e `setDate(hoje)` não emitiria
    # `dateChanged` — a asserção passaria sem nunca exercitar o limite.
    page.filtro_data_fim.setDate(QDate(ontem.year, ontem.month, ontem.day))
    assert page.table.rowCount() == 1
    assert ontem.strftime("%d/%m/%Y") in page.table.item(0, 5).text()


def test_limpar_filtros(qapp, catalogo):
    """Botão limpar filtros reseta produto, espécie, datas e restaura todos os dados."""
    movs = (
        _criar_movimento("MOV-001", code="PRD-001", kind=MovementKind.ENTRADA),
        _criar_movimento("MOV-002", code="PRD-002", kind=MovementKind.SAIDA),
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)

    # Aplica filtros
    page.filtro_produto_combo.setCurrentIndex(page.filtro_produto_combo.findData("PRD-001"))
    assert page.table.rowCount() == 1

    # Limpa filtros
    page.limpar_filtros_button.click()
    assert page.filtro_produto_combo.currentIndex() == 0
    assert page.filtro_especie_combo.currentIndex() == 0
    assert page.table.rowCount() == 2


def test_set_movements_preserva_filtros_ativos(qapp, catalogo):
    """Chamar set_movements (ex: após registrar/confirmar) preserva filtros ativos."""
    page = MovimentacoesPage(catalogo)
    page.set_movements((
        _criar_movimento("MOV-001", code="PRD-001"),
        _criar_movimento("MOV-002", code="PRD-002"),
    ))

    # Ativa filtro por PRD-002
    page.filtro_produto_combo.setCurrentIndex(page.filtro_produto_combo.findData("PRD-002"))
    assert page.table.rowCount() == 1

    # Nova carga com uma movimentação a mais para PRD-002
    page.set_movements((
        _criar_movimento("MOV-001", code="PRD-001"),
        _criar_movimento("MOV-002", code="PRD-002"),
        _criar_movimento("MOV-003", code="PRD-002"),
    ))

    # O filtro por PRD-002 continua ativo e exibe as 2 movimentações
    assert page.filtro_produto_combo.currentData() == "PRD-002"
    assert page.table.rowCount() == 2
    assert "2 registro(s)" in page.paginacao_label.text()


def test_filtro_sem_resultado_mostra_mensagem_adequada(qapp, catalogo):
    """Quando o filtro não encontra nenhuma linha, exibe aviso específico de filtro."""
    movs = (_criar_movimento("MOV-001", code="PRD-001"),)
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)

    # Filtra por espécie SAIDA quando só há ENTRADA
    page.filtro_especie_combo.setCurrentIndex(page.filtro_especie_combo.findData(MovementKind.SAIDA))

    assert page.table.rowCount() == 0
    assert page.list_state_label.isVisibleTo(page)
    assert "corresponde aos filtros" in page.list_state_label.text()


def test_filtro_especie_com_rotulo_real_da_aplicacao(qapp, catalogo):
    """Garante que tanto 'Entrada' quanto 'Saída' (rótulos da tabela) filtram perfeitamente."""
    movs = (
        ("1", "PRD-001", "Teclado", "Entrada", 5, "Confirmada", "—", "Hoje, 10:00", "—", "—"),
        ("2", "PRD-001", "Teclado", "Saída", 2, "Confirmada", "—", "Hoje, 11:00", "—", "—"),
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)
    assert page.table.rowCount() == 2

    # Filtra por Entrada
    page.filtro_especie_combo.setCurrentIndex(page.filtro_especie_combo.findData(MovementKind.ENTRADA))
    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "Entrada"

    # Filtra por Saída
    page.filtro_especie_combo.setCurrentIndex(page.filtro_especie_combo.findData(MovementKind.SAIDA))
    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "Saída"


def test_filtro_periodo_presets(qapp, catalogo):
    """Testa os seletores rápidos de período: Hoje, Últimos 7 dias, etc."""
    hoje = date.today()
    ontem = hoje - timedelta(days=1)
    antiga = hoje - timedelta(days=20)

    movs = (
        ("1", "PRD-001", "P1", "Entrada", 1, "Confirmada", "—", "Hoje, 10:00", "—", "—"),
        ("2", "PRD-001", "P1", "Entrada", 1, "Confirmada", "—", "Ontem, 15:00", "—", "—"),
        ("3", "PRD-001", "P1", "Entrada", 1, "Confirmada", "—", antiga.strftime("%d/%m/%Y"), "—", "—"),
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)
    assert page.table.rowCount() == 3

    # Preset Hoje
    page.filtro_periodo_combo.setCurrentIndex(page.filtro_periodo_combo.findData("hoje"))
    assert page.table.rowCount() == 1
    assert "Hoje" in page.table.item(0, 5).text()

    # Preset Últimos 7 dias
    page.filtro_periodo_combo.setCurrentIndex(page.filtro_periodo_combo.findData("7d"))
    assert page.table.rowCount() == 2


def test_novas_movimentacoes_aparecem_com_filtros_ativos(qapp, request, sem_dialogos):
    """Novas movimentações registradas na tela aparecem sob filtros ativos de Tipo e Período."""
    from stockflow.presentation.windows.main_window import MainWindow
    from stockflow.presentation.demo_accounts import conta_por_papel
    from stockflow.domain.enums.user_role import UserRole

    window = MainWindow(conta_por_papel(UserRole.ADMIN).session())
    request.addfinalizer(window.close)
    window.show_page("movimentacoes")
    page = window.movimentacoes_page

    # Aplica filtro de Tipo: Entrada
    page.filtro_especie_combo.setCurrentIndex(page.filtro_especie_combo.findData(MovementKind.ENTRADA))
    # Aplica filtro de Período: Hoje
    page.filtro_periodo_combo.setCurrentIndex(page.filtro_periodo_combo.findData("hoje"))

    linhas_antes = page.table.rowCount()

    # Lança nova movimentação de Entrada
    page.produto_combo.setCurrentIndex(1)
    page.especie_combo.setCurrentIndex(page.especie_combo.findData(MovementKind.ENTRADA))
    page.fornecedor_combo.setCurrentIndex(1)
    page.quantidade_input.setValue(3)
    page.registrar_button.click()

    # A nova movimentação DEVE aparecer na tabela mesmo com os filtros ativos!
    assert sem_dialogos == [], f"a tela recusou o lançamento: {sem_dialogos}"
    assert page.table.rowCount() == linhas_antes + 1
    assert page.table.item(0, 1).text() == "Entrada"
    assert "Hoje" in page.table.item(0, 5).text()


def test_preset_de_7_dias_cobre_sete_dias_e_nao_oito(qapp, catalogo):
    """O preset de 7 dias inclui hoje e os 6 anteriores; o sétimo dia atrás fica fora."""
    hoje = date.today()
    movs = (
        _criar_movimento("MOV-001", when=(hoje - timedelta(days=6)).strftime("%d/%m/%Y")),
        _criar_movimento("MOV-002", when=(hoje - timedelta(days=7)).strftime("%d/%m/%Y")),
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)

    page.filtro_periodo_combo.setCurrentIndex(page.filtro_periodo_combo.findData("7d"))

    assert page.table.rowCount() == 1
    assert (hoje - timedelta(days=6)).strftime("%d/%m/%Y") in page.table.item(0, 5).text()


def test_preset_de_30_dias_cobre_trinta_dias_e_nao_trinta_e_um(qapp, catalogo):
    """O preset de 30 dias inclui hoje e os 29 anteriores; o trigésimo fica fora."""
    hoje = date.today()
    movs = (
        _criar_movimento("MOV-001", when=(hoje - timedelta(days=29)).strftime("%d/%m/%Y")),
        _criar_movimento("MOV-002", when=(hoje - timedelta(days=30)).strftime("%d/%m/%Y")),
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)

    page.filtro_periodo_combo.setCurrentIndex(page.filtro_periodo_combo.findData("30d"))

    assert page.table.rowCount() == 1
    assert (hoje - timedelta(days=29)).strftime("%d/%m/%Y") in page.table.item(0, 5).text()


def test_paginar_durante_erro_de_carga_nao_reexibe_dados_velhos(qapp, catalogo):
    """Com o aviso de falha na tela, paginar não pode trazer a tabela obsoleta de volta."""
    movs = tuple(_criar_movimento(f"MOV-{i:03d}") for i in range(PAGE_SIZE + 1))
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)
    page.show_load_error("conexão perdida")
    assert not page.table.isVisibleTo(page)

    page.proximo_button.click()

    assert not page.table.isVisibleTo(page)
    assert page.load_error_label.isVisibleTo(page)


def test_filtrar_durante_erro_de_carga_nao_reexibe_dados_velhos(qapp, catalogo):
    """Idem para filtrar: o estado de erro manda até que uma carga nova chegue."""
    movs = (
        _criar_movimento("MOV-001", code="PRD-001"),
        _criar_movimento("MOV-002", code="PRD-002"),
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)
    page.show_load_error("conexão perdida")

    page.filtro_produto_combo.setCurrentIndex(page.filtro_produto_combo.findData("PRD-001"))

    assert not page.table.isVisibleTo(page)
    assert not page.list_state_label.isVisibleTo(page)
    assert page.load_error_label.isVisibleTo(page)


def test_reload_products_mantem_filtro_de_produto_que_ainda_tem_historico(qapp, catalogo):
    """Produto desativado e fora do catálogo continua filtrável enquanto houver histórico dele."""
    movs = (
        _criar_movimento("MOV-001", code="PRD-001"),
        _criar_movimento("MOV-002", code="PRD-002"),
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)
    page.filtro_produto_combo.setCurrentIndex(page.filtro_produto_combo.findData("PRD-002"))
    assert page.table.rowCount() == 1

    del catalogo["PRD-002"]
    page.reload_products(catalogo)

    assert page.filtro_produto_combo.currentData() == "PRD-002"
    assert page.table.rowCount() == 1


def test_reload_products_que_perde_o_produto_filtrado_recalcula_a_tela(qapp, catalogo):
    """Se a opção filtrada some de vez, a tabela volta a mostrar tudo — sem 'filtro ativo' mentindo."""
    movs = (_criar_movimento("MOV-001", code="PRD-001"),)
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)
    page.filtro_produto_combo.setCurrentIndex(page.filtro_produto_combo.findData("PRD-002"))
    assert page.table.rowCount() == 0

    del catalogo["PRD-002"]
    page.reload_products(catalogo)

    assert page.filtro_produto_combo.currentData() is None
    assert page.table.rowCount() == 1
    assert "filtro ativo" not in page.subtitle.text()


def test_apply_permission_preserva_a_pagina_atual(qapp, catalogo):
    """Reaplicar a permissão redesenha os botões da linha sem tirar o usuário da página."""
    movs = tuple(
        _criar_movimento(f"MOV-{i:03d}", status=MovementStatus.PENDENTE)
        for i in range(PAGE_SIZE + 1)
    )
    page = MovimentacoesPage(catalogo)
    page.set_movements(movs)
    page.proximo_button.click()
    assert "Página 2 de 2" in page.paginacao_label.text()

    page.apply_permission(False)

    assert "Página 2 de 2" in page.paginacao_label.text()
    assert page.table.rowCount() == 1
    acoes = page.table.cellWidget(0, ACTIONS_COLUMN)
    confirmar, cancelar, detalhes = acoes.findChildren(QPushButton)
    assert not confirmar.isEnabled()
    assert not cancelar.isEnabled()
    assert detalhes.isEnabled()  # Consulta de detalhes não altera movimentações.
