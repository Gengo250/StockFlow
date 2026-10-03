import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from stockflow.presentation.styles import inventory


class StockTable(QFrame):
    product_edit_requested = Signal(object)

    def __init__(self, products):
        super().__init__()
        self.setStyleSheet(inventory.TABLE_CARD_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.table = QTableWidget(len(products), 7)
        self.table.setHorizontalHeaderLabels(
            ["Código", "Produto", "Categoria", "Estoque", "Preço", "Status", "Ações"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setStyleSheet(inventory.TABLE_QSS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for row, product in enumerate(products):
            for column, value in enumerate(product):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setForeground(Qt.blue)
                self.table.setItem(row, column, item)
            self.table.setCellWidget(row, 6, self._create_actions(product))
        self.table.verticalHeader().setDefaultSectionSize(62)
        layout.addWidget(self.table)

    def _create_actions(self, product):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        edit = self._action_button("fa5s.pen", "Editar produto", "#EFF6FF")
        edit.clicked.connect(lambda: self.product_edit_requested.emit(product))
        layout.addWidget(edit)
        layout.addWidget(self._action_button("fa5s.trash-alt", "Excluir produto", "#FEF2F2"))
        return container

    @staticmethod
    def _action_button(icon, tooltip, hover_color):
        button = QPushButton()
        button.setIcon(qta.icon(icon, color="#94A3B8"))
        button.setFixedSize(28, 28)
        button.setToolTip(tooltip)
        button.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; border: none; }}
            QPushButton:hover {{ background-color: {hover_color}; border-radius: 6px; }}
        """)
        return button
