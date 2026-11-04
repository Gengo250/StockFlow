"""Páginas longas devem caber na janela e manter as ações alcançáveis."""
import pytest
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QScrollArea
from stockflow.presentation.demo_accounts import conta_admin
from stockflow.presentation.windows.main_window import MainWindow


@pytest.mark.parametrize("size", [(1024, 768), (1366, 768)])
def test_navigation_preserves_requested_viewport(qapp, monkeypatch, tmp_path, size):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    window = MainWindow(conta_admin().session())
    try:
        window.resize(*size)
        window.show()
        for key, page in window.page_widgets.items():
            window.show_page(key)
            qapp.processEvents()
            assert window.size() == QSize(*size), key
            assert window.pages.currentWidget() is page
            # O conteúdo pode ser maior, mas deve haver uma área rolável.
            scroll = page.parentWidget().parentWidget()
            assert isinstance(scroll, QScrollArea)
            assert scroll.viewport().width() <= size[0] - window.sidebar.width()
        window.show_page("vendas")
        page = window.vendas_page
        scroll = page.parentWidget().parentWidget()
        assert scroll.horizontalScrollBar().maximum() == 0, (
            "Os filtros do histórico não podem alargar o formulário de venda"
        )
        scroll.ensureWidgetVisible(page.save_button)
        qapp.processEvents()
        assert scroll.viewport().rect().intersects(page.save_button.rect().translated(
            page.save_button.mapTo(scroll.viewport(), page.save_button.rect().topLeft())))
    finally:
        window.close()


def test_a_sidebar_nao_dita_a_altura_minima_da_janela(qapp):
    """Item de menu novo não pode empurrar a janela para fora da tela.

    A sidebar cresce um botão a cada área nova e chegou a 767px de altura
    mínima com nove itens — um pixel abaixo de 1366x768, que é resolução
    comum de notebook. O décimo item (Indicadores, US16) estourou o limite e
    a janela passou a abrir 39px mais alta do que o pedido, em TODAS as
    telas, não só na nova.

    Raspar espaçamento compraria um item e devolveria o problema no
    seguinte. O menu rola; a janela não cresce.
    """
    from stockflow.presentation.widgets.sidebar import Sidebar

    sidebar = Sidebar()
    try:
        assert sidebar.minimumSizeHint().height() <= 600
    finally:
        sidebar.deleteLater()
