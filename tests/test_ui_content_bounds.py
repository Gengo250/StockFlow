"""Rendered content must remain inside its interactive surface after theming."""
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QLabel, QPushButton

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.presentation.pages.products import ProductsPage
from stockflow.presentation.pages.clientes import ClientesPage


def test_catalog_cards_keep_product_name_and_price_visible(qapp):
    page = ProductsPage(dict(DEMO_PRODUCTS))
    page.resize(1100, 760)
    page.show()
    try:
        qapp.processEvents()
        for card in page.cards.values():
            for name in ("productName", "productPrice"):
                label = card.findChild(QLabel, name)
                assert label.height() >= label.fontMetrics().height(), (name, label.size())
                bounds = QRect(label.mapTo(card, QPoint()), label.size())
                assert card.rect().contains(bounds), (name, card.size(), bounds)
    finally:
        page.close()


def test_client_row_actions_fit_inside_their_cells(qapp):
    page = ClientesPage(session=conta_por_papel(UserRole.ADMIN).session())
    page.resize(1100, 760)
    page.show()
    try:
        qapp.processEvents()
        for row in range(page.table.rowCount()):
            cell = page.table.cellWidget(row, 5)
            for button in cell.findChildren(QPushButton):
                bounds = QRect(button.mapTo(cell, QPoint()), button.size())
                assert cell.rect().contains(bounds), (button.text(), cell.size(), bounds)
    finally:
        page.close()


def test_primary_action_has_visible_keyboard_focus(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    from stockflow.presentation.styles.design_system import button_qss

    panel = QWidget()
    layout = QVBoxLayout(panel)
    primary = QPushButton("Salvar alterações")
    primary.setFixedHeight(40)
    primary.setStyleSheet(button_qss(primary=True))
    other = QPushButton("Cancelar")
    layout.addWidget(primary)
    layout.addWidget(other)
    panel.show()
    try:
        other.setFocus()
        qapp.processEvents()
        unfocused = primary.grab().toImage()
        primary.setFocus(Qt.TabFocusReason)
        qapp.processEvents()
        assert primary.hasFocus()
        assert primary.grab().toImage() != unfocused
    finally:
        panel.close()


def test_styled_combobox_keeps_a_visible_dropdown_affordance(qapp):
    from PySide6.QtWidgets import QComboBox
    from stockflow.presentation.styles.design_system import field_qss

    combo = QComboBox()
    combo.addItems(["Todos", "Ativos", "Inativos"])
    combo.setStyleSheet(field_qss())
    combo.resize(240, 40)
    combo.show()
    try:
        qapp.processEvents()
        image = combo.grab().toImage()
        # Inspect only the arrow area, excluding the border and the text.
        assert any(image.pixelColor(x, y).lightness() < 180
                   for x in range(218, 233) for y in range(14, 27))
    finally:
        combo.close()


def test_stock_product_names_remain_readable_in_a_small_viewport(qapp):
    from stockflow.presentation.pages.estoque import EstoquePage
    from stockflow.presentation.widgets.stock_table import StockTable

    page = EstoquePage()
    page.resize(740, 600)
    page.show()
    try:
        qapp.processEvents()
        table = page.findChild(StockTable).table
        required = max(table.fontMetrics().horizontalAdvance(table.item(row, 1).text())
                       for row in range(table.rowCount()))
        assert table.columnWidth(1) >= required
    finally:
        page.close()
