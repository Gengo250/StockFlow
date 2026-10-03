import qtawesome as qta
from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.presentation.styles import inventory
from stockflow.presentation.widgets.stock_table import StockTable


class EstoquePage(QWidget):
    product_edit_requested = Signal(object)

    def __init__(self):
        super().__init__()
        self.setObjectName("estoquePage")
        self.setStyleSheet(inventory.PAGE_QSS)
        self.produtos = [
            (product.code, product.name, product.category, product.stock,
             product.sale_price, product.stock_status)
            for product in DEMO_PRODUCTS.values()
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)
        layout.addLayout(self._create_header())
        layout.addLayout(self._create_filters())
        self.stock_table = StockTable(self.produtos)
        self.stock_table.product_edit_requested.connect(self.product_edit_requested.emit)
        self.table = self.stock_table.table
        layout.addWidget(self.stock_table)

    def _create_header(self):
        layout = QHBoxLayout()
        container = QWidget()
        texts = QVBoxLayout(container)
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        title = QLabel("Controle de Estoque")
        title.setStyleSheet(inventory.TITLE_QSS)
        subtitle = QLabel(f"{len(self.produtos)} produtos cadastrados")
        subtitle.setStyleSheet(inventory.SUBTITLE_QSS)
        texts.addWidget(title)
        texts.addWidget(subtitle)
        self.new_product_button = QPushButton("Novo Produto")
        self.new_product_button.setIcon(qta.icon("fa5s.plus", color="white"))
        self.new_product_button.setIconSize(QSize(14, 14))
        self.new_product_button.setFixedHeight(40)
        self.new_product_button.setStyleSheet(inventory.NEW_BUTTON_QSS)
        layout.addWidget(container)
        layout.addStretch()
        layout.addWidget(self.new_product_button)
        return layout

    def _create_filters(self):
        layout = QHBoxLayout()
        layout.setSpacing(10)
        search = QLineEdit()
        search.setPlaceholderText("Buscar produto ou código...")
        search.setFixedHeight(44)
        search.addAction(qta.icon("fa5s.search", color="#94A3B8"), QLineEdit.LeadingPosition)
        search.setStyleSheet(inventory.SEARCH_QSS)
        layout.addWidget(search, 1)
        self.filter_buttons = []
        for index, text in enumerate(("Todos", "Normal", "Baixo", "Crítico")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setFixedHeight(44)
            button.setMinimumWidth(82)
            button.setStyleSheet(inventory.FILTER_QSS)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, btn=button: self.select_filter(btn))
            self.filter_buttons.append(button)
            layout.addWidget(button)
        return layout

    def select_filter(self, selected_button):
        for button in self.filter_buttons:
            button.setChecked(button == selected_button)
