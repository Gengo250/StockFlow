from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stockflow.application.dto.purchase_input import PurchaseInput, PurchaseItemInput
from stockflow.domain.enums.purchase_status import PurchaseStatus
from stockflow.presentation.styles import design_system as ds
from stockflow.presentation.styles import inventory


class PurchasesPage(QWidget):
    create_requested = Signal(object)
    receive_requested = Signal(str)

    def __init__(self, products=None, parent=None):
        super().__init__(parent)
        self.products = {} if products is None else products
        self._suppliers = ()
        self._items: list[PurchaseItemInput] = []
        self._purchases = ()
        self._can_write = False
        self.setObjectName("purchasesPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN
        )
        layout.setSpacing(ds.SECTION_GAP)

        title = QLabel("Compras")
        title.setStyleSheet(inventory.TITLE_QSS)
        subtitle = QLabel(
            "Monte uma compra em rascunho e receba todos os itens de uma vez."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(inventory.SUBTITLE_QSS)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.form_card = QFrame()
        self.form_card.setObjectName("purchaseFormCard")
        form_layout = QVBoxLayout(self.form_card)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form_layout.setSpacing(10)

        supplier_row = QHBoxLayout()
        self.supplier_combo = QComboBox()
        self.supplier_combo.setAccessibleName("Fornecedor da compra")
        self.supplier_combo.addItem("Selecione um fornecedor...", None)
        supplier_row.addWidget(self.supplier_combo, 1)

        self.product_combo = QComboBox()
        self.product_combo.setAccessibleName("Produto da compra")
        self.product_combo.addItem("Selecione um produto...", None)
        supplier_row.addWidget(self.product_combo, 2)

        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 1_000_000)
        self.quantity_input.setAccessibleName("Quantidade do item")
        supplier_row.addWidget(self.quantity_input)

        self.add_item_button = QPushButton("Adicionar item")
        self.add_item_button.clicked.connect(self._add_item)
        supplier_row.addWidget(self.add_item_button)
        form_layout.addLayout(supplier_row)

        self.items_table = QTableWidget(0, 3)
        self.items_table.setHorizontalHeaderLabels(["Produto", "Quantidade", ""])
        self.items_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.items_table.verticalHeader().hide()
        self.items_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.items_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.items_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        form_layout.addWidget(self.items_table)

        form_actions = QHBoxLayout()
        self.feedback_label = QLabel()
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setStyleSheet(inventory.LOAD_ERROR_QSS)
        form_actions.addWidget(self.feedback_label, 1)
        self.create_button = QPushButton("Criar rascunho")
        self.create_button.setObjectName("primaryButton")
        self.create_button.clicked.connect(self._create)
        form_actions.addWidget(self.create_button)
        form_layout.addLayout(form_actions)
        layout.addWidget(self.form_card)

        self.purchases_table = QTableWidget(0, 5)
        self.purchases_table.setHorizontalHeaderLabels(
            ["Compra", "Fornecedor", "Itens", "Situação", "Ação"]
        )
        self.purchases_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.purchases_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.purchases_table.verticalHeader().hide()
        header = self.purchases_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        layout.addWidget(self.purchases_table, 1)

        self.list_state_label = QLabel("Nenhuma compra cadastrada.")
        self.list_state_label.setAlignment(Qt.AlignCenter)
        self.list_state_label.setWordWrap(True)
        self.list_state_label.setStyleSheet(inventory.LIST_STATE_QSS)
        layout.addWidget(self.list_state_label)
        self.reload_products(self.products)

    def reload_products(self, products=None):
        if products is not None:
            self.products = products
        selected = self.product_combo.currentData()
        self.product_combo.clear()
        self.product_combo.addItem("Selecione um produto...", None)
        for product in sorted(self.products.values(), key=lambda item: item.code):
            if product.active:
                self.product_combo.addItem(
                    f"{product.code} — {product.name}", product.code
                )
        index = self.product_combo.findData(selected)
        if index >= 0:
            self.product_combo.setCurrentIndex(index)

    def set_suppliers(self, suppliers):
        selected = self.supplier_combo.currentData()
        self._suppliers = tuple(s for s in suppliers if s.active)
        self.supplier_combo.clear()
        self.supplier_combo.addItem("Selecione um fornecedor...", None)
        for supplier in self._suppliers:
            self.supplier_combo.addItem(supplier.name, supplier.supplier_id)
        index = self.supplier_combo.findData(selected)
        if index >= 0:
            self.supplier_combo.setCurrentIndex(index)

    def apply_permission(self, allowed: bool):
        self._can_write = bool(allowed)
        self.supplier_combo.setEnabled(self._can_write)
        self.product_combo.setEnabled(self._can_write)
        self.quantity_input.setEnabled(self._can_write)
        self.add_item_button.setEnabled(self._can_write)
        self.create_button.setEnabled(self._can_write)
        self._render_items()
        self.set_purchases(self._purchases)

    def _add_item(self):
        code = self.product_combo.currentData()
        if code is None:
            self.show_error("Selecione um produto.")
            return
        self._items.append(PurchaseItemInput(code, self.quantity_input.value()))
        self.feedback_label.clear()
        self._render_items()

    def _remove_item(self, index):
        if 0 <= index < len(self._items):
            self._items.pop(index)
            self._render_items()

    def _render_items(self):
        self.items_table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            product = self.products.get(item.product_code)
            name = product.name if product is not None else item.product_code
            self.items_table.setItem(
                row, 0, QTableWidgetItem(f"{item.product_code} — {name}")
            )
            self.items_table.setItem(row, 1, QTableWidgetItem(str(item.quantity)))
            remove = QPushButton("Remover")
            remove.setEnabled(self._can_write)
            remove.clicked.connect(
                lambda _=False, index=row: self._remove_item(index)
            )
            self.items_table.setCellWidget(row, 2, remove)

    def _create(self):
        supplier_id = self.supplier_combo.currentData()
        if supplier_id is None:
            self.show_error("Selecione o fornecedor da compra.")
            return
        if not self._items:
            self.show_error("Adicione pelo menos um item à compra.")
            return
        self.create_requested.emit(
            PurchaseInput(str(supplier_id), tuple(self._items))
        )

    def purchase_created(self):
        self._items.clear()
        self.supplier_combo.setCurrentIndex(0)
        self.feedback_label.clear()
        self._render_items()

    def set_purchases(self, purchases):
        self._purchases = tuple(purchases)
        self.list_state_label.setStyleSheet(inventory.LIST_STATE_QSS)
        self.purchases_table.setRowCount(len(self._purchases))
        self.purchases_table.setVisible(bool(self._purchases))
        self.list_state_label.setVisible(not self._purchases)
        for row, purchase in enumerate(self._purchases):
            purchase_id = str(purchase.purchase_id)
            self.purchases_table.setItem(
                row, 0, QTableWidgetItem(purchase_id[-8:])
            )
            self.purchases_table.setItem(
                row, 1, QTableWidgetItem(purchase.supplier_name or purchase.supplier_id)
            )
            summary = "; ".join(
                f"{item.product_code} — {item.product_name} × {item.quantity}"
                for item in purchase.items
            )
            self.purchases_table.setItem(row, 2, QTableWidgetItem(summary))
            self.purchases_table.setItem(
                row, 3, QTableWidgetItem(purchase.status.label)
            )
            action = QPushButton("Receber")
            draft = purchase.status is PurchaseStatus.RASCUNHO
            action.setEnabled(draft and self._can_write)
            action.setVisible(draft)
            action.clicked.connect(
                lambda _=False, identifier=purchase_id:
                self.receive_requested.emit(identifier)
            )
            self.purchases_table.setCellWidget(row, 4, action)
        if not self._purchases:
            self.list_state_label.setText("Nenhuma compra cadastrada.")

    def show_error(self, error):
        self.feedback_label.setText(str(error))

    def show_load_error(self, error):
        self.purchases_table.setRowCount(0)
        self.purchases_table.hide()
        self.list_state_label.setText(
            f"Não foi possível carregar as compras.\n{error}"
        )
        self.list_state_label.setStyleSheet(inventory.LOAD_ERROR_QSS)
        self.list_state_label.show()
