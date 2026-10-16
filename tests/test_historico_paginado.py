"""Testes da consulta paginada do histórico de movimentações e seus filtros.

Cobre a navegação entre páginas, filtros (produto, espécie, período),
preservação de filtros em recargas e estados vazios.
"""

from datetime import date, datetime, timedelta
import pytest
from PySide6.QtCore import QDate

from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.movement_status import MovementStatus
from stockflow.presentation.demo_products import Product
from stockflow.presentation.pages.movimentacoes import (
    COLUMNS,
    MOV_CODE,
    MOV_ID,
    MOV_KIND,
    MOV_NAME,
    MOV_NOTE,
    MOV_QTY,
    MOV_REASON,
    MOV_STATUS,
    MOV_SUPPLIER,
    MOV_WHEN,
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

    # Filtra período cobrindo de ontem até hoje
    page.filtro_data_inicio.setDate(QDate(ontem.year, ontem.month, ontem.day))
    page.filtro_data_fim.setDate(QDate(hoje.year, hoje.month, hoje.day))

    assert page.table.rowCount() == 2
    assert "2 registro(s)" in page.paginacao_label.text()


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
    page.filtro_especie_combo.setCurrentIndex(page.filtro_especie_combo.findData(MovementKind.SAIDA.value))

    assert page.table.rowCount() == 0
    assert page.list_state_label.isVisibleTo(page)
    assert "corresponde aos filtros" in page.list_state_label.text()
