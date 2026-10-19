"""Reproduções pendentes do remoto, preservadas para a próxima rodada.

Executar explicitamente: pytest docs/auditoria/2026-10-19/test_pending_remote_merge.py
Há quatro falhas conhecidas; este arquivo não faz parte da suíte de aceite.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from stockflow.application.dto.movement_input import MovementInput
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.infrastructure.repositories.movement_mapper import row_to_movement
from stockflow.presentation.demo_accounts import conta_admin
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.presentation.pages.movimentacoes import ACTIONS_COLUMN, MovimentacoesPage
from stockflow.presentation.pages.novo_produto import NovoProdutoPage
from stockflow.presentation.windows.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_movement_details_open_from_history_and_return(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    window = MainWindow(conta_admin().session())
    try:
        window.show_page("movimentacoes")
        window.movement_service.register(window.session, MovementInput(
            product_code="PRD-009", kind=MovementKind.SAIDA, quantity=1,
            note="Movimentação de teste",
        ))
        window._recarregar_movimentacoes()
        page = window.movimentacoes_page
        buttons = page.table.cellWidget(0, ACTIONS_COLUMN).findChildren(QPushButton)
        next(b for b in buttons if b.toolTip() == "Ver detalhes da movimentação").click()
        details = window.pages.currentWidget()
        assert details is not page
        assert details.values["note"].text() == "Movimentação de teste"
        assert details.values["user"].text() == window.session.user_id
        details.back_button.click()
        assert window.pages.currentWidget() is page
    finally:
        window.close()


def test_movement_author_reaches_filter_from_repository_row(qapp):
    page = MovimentacoesPage()
    try:
        rows = [row_to_movement(dict(id=actor, created_by=actor, kind="ENTRADA",
                                   quantity=1, status="PENDENTE"), "P1", "Produto")
                for actor in ("usuario-a", "usuario-b")]
        page.set_movements(rows)
        index = page.filtro_usuario_combo.findData("usuario-b")
        assert index > 0
        page.filtro_usuario_combo.setCurrentIndex(index)
        assert page.table.rowCount() == 1
        assert page.table.item(0, 8).text() == "usuario-b"
        assert "filtro ativo" in page.subtitle.text()
        page.limpar_filtros()
        assert page.table.rowCount() == 2
    finally:
        page.close()


@pytest.mark.parametrize("maximum", [None, 0, 15])
def test_product_edit_preserves_optional_maximum(qapp, maximum):
    page = NovoProdutoPage(edit_mode=True)
    try:
        product = replace(next(iter(DEMO_PRODUCTS.values())), minimum_stock=None,
                          maximum_stock=maximum)
        page.load_product(product)
        assert page.collect_input().maximum_stock == maximum
    finally:
        page.close()


def test_edit_inventory_tuple_does_not_require_a_maximum(qapp):
    page = NovoProdutoPage(edit_mode=True)
    try:
        page.load_product(("P1", "Produto", "Categoria", "3", "2", "R$ 5,00", "Normal", True))
        assert page.collect_input().maximum_stock is None
    finally:
        page.close()


def test_supplier_search_is_visible_in_the_window(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    window = MainWindow(conta_admin().session())
    try:
        window.show()
        window.show_page("fornecedores")
        qapp.processEvents()
        assert window.suppliers_page.search_input.isVisibleTo(window.suppliers_page)
        assert window.suppliers_page.search_input.parentWidget() is window.suppliers_page
    finally:
        window.close()
