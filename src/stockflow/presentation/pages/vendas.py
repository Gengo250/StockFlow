from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stockflow.application.dto.sale_item import SaleItemInput, SaleItemValidator
from stockflow.application.services.product_selection_service import ProductSelectionService
from stockflow.application.services.sale_service import SaleService, calculate_total_from_items, parse_total
from stockflow.domain.enums.operation_kind import OperationKind
from stockflow.domain.exceptions.inactive_product import InactiveProductError
from stockflow.domain.exceptions.product_not_found import ProductNotFoundError
from stockflow.domain.permissions import can_manage_clients
from stockflow.infrastructure.repositories.demo_client_repository import DemoClientRepository
from stockflow.infrastructure.repositories.demo_product_repository import DemoProductRepository
from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
from stockflow.presentation.demo_products import DEMO_PRODUCTS


class VendasPage(QWidget):
    """Montagem e confirmação de vendas compostas por vários produtos."""

    sale_registered = Signal()

    def __init__(self, products=None, product_selection=None, parent=None, service=None, session=None):
        super().__init__(parent)
        self.setObjectName("vendasPage")
        self.setStyleSheet("""
            QWidget#vendasPage { background-color: #F0F5FF; }
            QLabel { background-color: transparent; }
            QFrame#card {
                background-color: #FFFFFF;
                border: 1px solid #DBEAFE;
                border-radius: 16px;
            }
            QLineEdit, QComboBox {
                background-color: white;
                color: #0F172A;
                border: 1px solid #BFDBFE;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QPushButton#primaryButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover { background-color: #1D4ED8; }
            QTableWidget { background-color: #FFFFFF; border: none; }
            QHeaderView::section {
                background-color: #F8FBFF;
                color: #64748B;
                border: none;
                border-bottom: 1px solid #DBEAFE;
                padding: 10px;
                font-size: 12px;
                font-weight: 600;
            }
        """)

        self.products = dict(DEMO_PRODUCTS) if products is None else products
        self.product_selection = product_selection or ProductSelectionService(
            DemoProductRepository(self.products)
        )
        self.session = session
        if service is None:
            self.movement_repository = DemoMovementRepository(self.products)
            self.service = SaleService(
                DemoSaleRepository(self.products, self.movement_repository),
                DemoClientRepository(),
                DemoProductRepository(self.products),
            )
        else:
            self.service = service
            self.movement_repository = getattr(
                self.service.repository, "_movement_repository", None
            )
        self.client_repository = self.service.clients
        self.clientes = [
            {
                "id": client.client_id,
                "nome": client.name,
                "status": "Ativo" if client.active else "Inativo",
            }
            for client in self.client_repository.list_all()
        ]
        self.historico_vendas = self.service.list_sales()
        self._item_rows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)
        title = QLabel("Registro e Seleção de Vendas")
        title.setStyleSheet("color: #0F172A; font-size: 26px; font-weight: 700;")
        layout.addWidget(title)

        form_card = QFrame()
        form_card.setObjectName("card")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(12)
        form_title = QLabel("Nova Venda")
        form_title.setStyleSheet("color: #1E3A8A; font-size: 16px; font-weight: 600;")
        form_layout.addWidget(form_title)

        client_row = QHBoxLayout()
        self.cliente_combo = QComboBox()
        self.cliente_combo.setFixedHeight(42)
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #EF4444; font-size: 12px; font-weight: 500;")
        self.recarregar_clientes_disponiveis()
        self.cliente_combo.currentIndexChanged.connect(self._ao_selecionar_cliente)
        client_row.addWidget(self.cliente_combo, 2)
        client_row.addWidget(self.warning_label, 1)
        form_layout.addLayout(client_row)

        self.itens_frame = QFrame()
        self.itens_frame.setObjectName("card")
        self.itens_layout = QVBoxLayout(self.itens_frame)
        self.itens_layout.setContentsMargins(10, 10, 10, 10)
        self.itens_layout.setSpacing(8)
        form_layout.addWidget(self.itens_frame, 1)
        self._adicionar_linha_item()

        self.btn_adicionar_item = QPushButton("+ Outro Item")
        self.btn_adicionar_item.setObjectName("primaryButton")
        self.btn_adicionar_item.setFixedHeight(32)
        self.btn_adicionar_item.clicked.connect(self._adicionar_linha_item)
        form_layout.addWidget(self.btn_adicionar_item)

        total_row = QHBoxLayout()
        self.label_total = QLabel("Total: R$ 0,00")
        self.label_total.setStyleSheet("color: #0F172A; font-size: 14px; font-weight: 600;")
        self.label_total_value = QLabel("R$ 0,00")
        self.label_total_value.setStyleSheet("color: #059669; font-size: 14px;")
        self.save_button = QPushButton("Confirmar Venda")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setFixedHeight(42)
        self.save_button.setIcon(qta.icon("fa5s.check", color="white"))
        self.save_button.clicked.connect(self._registrar_venda)
        total_row.addWidget(self.label_total)
        total_row.addWidget(self.label_total_value, 1)
        total_row.addWidget(self.save_button)
        form_layout.addLayout(total_row)
        layout.addWidget(form_card)

        hist_title = QLabel("Histórico de Vendas Realizadas")
        hist_title.setStyleSheet("color: #0F172A; font-size: 18px; font-weight: 600;")
        layout.addWidget(hist_title)
        table_card = QFrame()
        table_card.setObjectName("card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["ID Venda", "Cliente Associado", "Produto(s)", "Valor Total", "Data"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        table_layout.addWidget(self.table)
        layout.addWidget(table_card, 1)
        self.atualizar_tabela_historico()
        self.apply_session(session)

    @property
    def itens(self):
        """Itens válidos da tela, preservando a ordem visual das linhas."""
        result = []
        for row in self._item_rows:
            code = self._code_from_data(row["combo"].currentData())
            quantity_text = row["quantity"].text().strip()
            if not code and not quantity_text:
                continue
            if not code:
                raise ValueError("Selecione um produto para cada quantidade informada.")
            if not quantity_text.isascii() or not quantity_text.isdecimal() or int(quantity_text) <= 0:
                raise ValueError(f"Informe uma quantidade inteira positiva para {code}.")
            result.append(SaleItemInput(
                product_code=code,
                quantity=int(quantity_text),
            ))
        return tuple(result)

    @property
    def produto_combo(self):
        return self._item_rows[0]["combo"]

    def apply_session(self, session):
        self.session = session
        self.save_button.setEnabled(can_manage_clients(session))

    def reload_sales(self):
        self.historico_vendas = self.service.list_sales()
        self.atualizar_tabela_historico()

    def recarregar_clientes_disponiveis(self):
        escolhido = self.cliente_combo.currentData() if hasattr(self, "cliente_combo") else None
        self.cliente_combo.clear()
        self.cliente_combo.addItem("Selecione um cliente...", None)
        for client in self.clientes:
            if self._cliente_ativo(client["id"]):
                self.cliente_combo.addItem(
                    f"{client['nome']} ({client['id']})", client
                )
        if escolhido:
            self._apontar_cliente(escolhido["id"])

    def _apontar_cliente(self, client_id):
        for index in range(self.cliente_combo.count()):
            data = self.cliente_combo.itemData(index)
            if data and data.get("id") == client_id:
                self.cliente_combo.setCurrentIndex(index)
                return True
        return False

    def selecionar_cliente_externo(self, nome):
        cliente = next((c for c in self.clientes if c["nome"] == nome), None)
        if cliente is None:
            self.warning_label.setText(f"O cliente {nome} não existe.")
            self.cliente_combo.setCurrentIndex(0)
            return False
        if not self._cliente_ativo(cliente["id"]):
            self.warning_label.setText(f"O cliente {nome} está inativo.")
            self.cliente_combo.setCurrentIndex(0)
            return False
        self._apontar_cliente(cliente["id"])
        self.warning_label.setText("")
        return True

    def _cliente_ativo(self, client_id):
        return any(
            client["id"] == client_id and client["status"] == "Ativo"
            for client in self.clientes
        )

    def _ao_selecionar_cliente(self, _index):
        if self.cliente_combo.currentData() is not None:
            self.warning_label.setText("")

    def reload_products(self, products=None):
        if products is not None:
            self.products = products
        selected_by_row = [
            self._code_from_data(row["combo"].currentData())
            for row in self._item_rows
        ]
        for row, selected in zip(self._item_rows, selected_by_row):
            self._preencher_combo_produtos(row["combo"], selected)
        self._atualizar_total()

    def recarregar_produtos_disponiveis(self):
        self.reload_products()

    def _adicionar_linha_item(self):
        frame = QFrame()
        frame.setStyleSheet("QFrame { border: none; }")
        row_layout = QHBoxLayout(frame)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        combo = QComboBox()
        combo.setFixedHeight(38)
        self._preencher_combo_produtos(combo)
        quantity = QLineEdit()
        quantity.setPlaceholderText("Qtd")
        quantity.setFixedHeight(38)
        quantity.setMaxLength(10)
        remove = QPushButton("Remover")
        remove.setFixedHeight(38)
        remove.setStyleSheet("QPushButton { background: transparent; color: #EF4444; border: none; }")
        subtotal = QLabel("R$ 0,00")
        subtotal.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row = {
            "frame": frame,
            "combo": combo,
            "quantity": quantity,
            "subtotal": subtotal,
        }
        self._item_rows.append(row)
        combo.currentIndexChanged.connect(lambda _index, current=row: self._linha_mudou(current))
        quantity.textChanged.connect(lambda _text, current=row: self._linha_mudou(current))
        remove.clicked.connect(lambda _checked=False, current=row: self._remover_linha_item(current))
        row_layout.addWidget(combo, 1)
        row_layout.addWidget(quantity, 1)
        row_layout.addWidget(subtotal, 0)
        row_layout.addWidget(remove)
        self.itens_layout.addWidget(frame)

    def _preencher_combo_produtos(self, combo, selected=None):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Selecione um produto...", None)
        for product in self.product_selection.available_products():
            combo.addItem(
                f"{product.name} ({product.code})",
                {"codigo": product.code, "nome": product.name},
            )
        if selected:
            index = next(
                (
                    i for i in range(combo.count())
                    if self._code_from_data(combo.itemData(i)) == selected
                ),
                -1,
            )
            if index >= 0:
                combo.setCurrentIndex(index)
            else:
                self.warning_label.setText(
                    f"O produto {selected} não está disponível para venda."
                )
        combo.blockSignals(False)

    def _linha_mudou(self, row):
        code = self._code_from_data(row["combo"].currentData())
        if code:
            try:
                self.product_selection.ensure_selectable(code, OperationKind.VENDA)
            except (InactiveProductError, ProductNotFoundError) as error:
                self.warning_label.setText(str(error))
                row["combo"].setCurrentIndex(0)
                self._atualizar_total()
                return
        self.warning_label.setText("")
        self._atualizar_total()

    def _remover_linha_item(self, row):
        if len(self._item_rows) == 1:
            row["combo"].setCurrentIndex(0)
            row["quantity"].clear()
        else:
            self._item_rows.remove(row)
            self.itens_layout.removeWidget(row["frame"])
            row["frame"].deleteLater()
        self.warning_label.setText("")
        self._atualizar_total()

    def selecionar_produto(self, codigo):
        try:
            self.product_selection.ensure_selectable(codigo, OperationKind.VENDA)
        except (InactiveProductError, ProductNotFoundError) as error:
            self.warning_label.setText(str(error))
            return False
        row = next(
            (
                item for item in self._item_rows
                if self._code_from_data(item["combo"].currentData()) is None
            ),
            None,
        )
        if row is None:
            self._adicionar_linha_item()
            row = self._item_rows[-1]
        index = next(
            (
                i for i in range(row["combo"].count())
                if self._code_from_data(row["combo"].itemData(i)) == codigo
            ),
            -1,
        )
        if index < 0:
            self._preencher_combo_produtos(row["combo"])
            index = next(
                (
                    i for i in range(row["combo"].count())
                    if self._code_from_data(row["combo"].itemData(i)) == codigo
                ),
                -1,
            )
        if index < 0:
            self.warning_label.setText(f"O produto {codigo} não está disponível para venda.")
            return False
        row["combo"].setCurrentIndex(index)
        if not row["quantity"].text():
            row["quantity"].setText("1")
        self.warning_label.setText("")
        self._atualizar_total()
        return True

    @staticmethod
    def _code_from_data(data):
        if isinstance(data, dict):
            return data.get("codigo")
        return data

    def _atualizar_total(self):
        for row in self._item_rows:
            row["subtotal"].setText("R$ 0,00")
        try:
            items = self.itens
            if not items:
                self.label_total.setText("Total: R$ 0,00")
                self.label_total_value.setText("R$ 0,00")
                return
            validator = SaleItemValidator(DemoProductRepository(self.products))
            validator.validate(items)
            codes = {item.product_code for item in items}
            prices = {
                code: parse_total(self.products[code].sale_price)
                for code in codes
            }
            total = calculate_total_from_items(items, prices)
            item_index = 0
            for row in self._item_rows:
                if self._code_from_data(row["combo"].currentData()) is None:
                    continue
                item = items[item_index]
                row["subtotal"].setText(
                    self._format_currency(
                        prices[item.product_code] * item.quantity
                    )
                )
                item_index += 1
        except ValueError as error:
            message = str(error)
            if "inativo" in message.casefold() or "não existe" in message.casefold():
                self.reload_products()
            self.warning_label.setText(message)
            total = Decimal("0.00")
        formatted = self._format_currency(total)
        self.label_total.setText(f"Total: {formatted}")
        self.label_total_value.setText(formatted)

    @staticmethod
    def _format_currency(amount):
        return f"R$ {amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    def _registrar_venda(self):
        client = self.cliente_combo.currentData()
        if not client:
            self.warning_label.setText("Selecione um cliente ativo válido.")
            return
        try:
            items = self.itens
            if not items:
                self.warning_label.setText("Adicione pelo menos um item à venda.")
                return
            registered = self.service.register(self.session, client["id"], items)
        except ValueError as error:
            message = str(error)
            if "inativo" in message.casefold() or "não existe" in message.casefold():
                self.reload_products()
            self.warning_label.setText(message)
            return
        except Exception as error:
            self.warning_label.setText(f"Erro ao registrar venda: {error}")
            return

        self.historico_vendas.insert(0, registered)
        self._limpar_linhas_itens()
        self._adicionar_linha_item()
        self.cliente_combo.setCurrentIndex(0)
        self.warning_label.setText("")
        self._atualizar_total()
        self.atualizar_tabela_historico()
        self.sale_registered.emit()

    def _limpar_linhas_itens(self):
        while self.itens_layout.count():
            item = self.itens_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._item_rows.clear()

    def atualizar_tabela_historico(self):
        self.table.setRowCount(len(self.historico_vendas))
        for row_index, sale in enumerate(self.historico_vendas):
            values = (
                sale["id"], sale["cliente"], sale["produto"],
                sale["valor"], sale["data"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_index, column, item)
