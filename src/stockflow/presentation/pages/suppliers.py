"""Cadastro, consulta e inativação lógica de fornecedores."""

from PySide6.QtCore import Qt, Signal
import qtawesome as qta
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from stockflow.application.dto.supplier_input import SupplierInput
from stockflow.application.services.supplier_service import SupplierService
from stockflow.domain.entities.supplier import Supplier
from stockflow.presentation.styles.suppliers import SUPPLIERS_QSS
from stockflow.presentation.styles import inventory
from stockflow.presentation.widgets.form_fields import _card, _card_header, _field, _combo


class SuppliersPage(QWidget):
    suppliers_changed = Signal()

    def __init__(self, service: SupplierService, session=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.session = session
        self._suppliers = ()
        self.last_error = None
        self.setObjectName("suppliersPage")
        self.setStyleSheet(SUPPLIERS_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(4)
        title = QLabel("Fornecedores")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Cadastre, consulte e mantenha fornecedores ativos ou inativos.")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Buscar por nome, CPF/CNPJ ou informações de contato"
        )
        self.search_input.setAccessibleName("Buscar fornecedores")
        self.search_input.setFixedHeight(42)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.addAction(
            qta.icon("fa5s.search", color="#94A3B8"), QLineEdit.LeadingPosition
        )
        self.search_input.textChanged.connect(self._filter_table)

        self.new_supplier_button = QPushButton("Novo fornecedor")
        self.new_supplier_button.setObjectName("primaryButton")
        self.new_supplier_button.setFixedHeight(42)
        self.new_supplier_button.setCursor(Qt.PointingHandCursor)
        self.new_supplier_button.setIcon(qta.icon("fa5s.plus", color="white"))
        self.new_supplier_button.clicked.connect(lambda: self.open_form())
        self.refresh_button = QPushButton("Atualizar")
        self.refresh_button.setObjectName("secondaryButton")
        self.refresh_button.setIcon(qta.icon("fa5s.sync-alt", color="#475569"))
        self.refresh_button.setFixedHeight(42)
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.reload_table)
        header.addWidget(self.refresh_button)
        header.addWidget(self.new_supplier_button)
        layout.addLayout(header)

        filters = _card("supplierFilters")
        filters.layout().setContentsMargins(18, 14, 18, 14)
        filter_row = QHBoxLayout()
        search_field = _field("Buscar fornecedor")
        search_field.layout().addWidget(self.search_input)
        filter_row.addWidget(search_field, 1)
        self.status_filter = _combo(["Todos", "Ativos", "Inativos"])
        self.status_filter.setAccessibleName("Situação do fornecedor")
        self.status_filter.currentIndexChanged.connect(lambda: self._filter_table(self.search_input.text()))
        status_field = _field("Situação")
        status_field.layout().addWidget(self.status_filter)
        filter_row.addWidget(status_field)
        filters.layout().addLayout(filter_row)
        layout.addWidget(filters)

        self.table_card = _card("suppliersTableCard")
        table_layout = self.table_card.layout()
        table_layout.addLayout(_card_header("fa5s.truck", "Fornecedores cadastrados", "Consulte os contatos e gerencie a situação dos seus parceiros."))
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Nome / razão social", "CPF/CNPJ", "E-mail", "Telefone",
                "Endereço", "Status", "Ações",
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(inventory.TABLE_QSS)
        self.table.verticalHeader().hide()
        header_view = self.table.horizontalHeader()
        header_view.setMinimumSectionSize(80)
        header_view.setSectionResizeMode(QHeaderView.Interactive)
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)
        for column, width in ((0, 200), (1, 120), (3, 125), (4, 100)):
            self.table.setColumnWidth(column, width)
        header_view.setSectionResizeMode(5, QHeaderView.Fixed)
        header_view.setSectionResizeMode(6, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 210)
        table_layout.addWidget(self.table, 1)
        layout.addWidget(self.table_card, 1)
        self.empty_label = QLabel("Nenhum fornecedor cadastrado.")
        self.empty_label.setObjectName("muted")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setTextFormat(Qt.PlainText)
        self.empty_label.setStyleSheet(inventory.LIST_STATE_QSS)
        table_layout.addWidget(self.empty_label)
        self.result_count = QLabel()
        self.result_count.setObjectName("muted")
        table_layout.addWidget(self.result_count)
        self.reload_table()

    def reload_table(self):
        try:
            self._suppliers = tuple(
                sorted(
                    self.service.list_suppliers(self.session),
                    key=lambda supplier: supplier.name.casefold(),
                )
            )
        except Exception as error:
            self.last_error = error
            self._suppliers = ()
            self.table.setRowCount(0)
            self.result_count.setText("Cadastro indisponível")
            self.empty_label.setStyleSheet(inventory.LOAD_ERROR_QSS)
            self.empty_label.setText(f"Não foi possível carregar fornecedores.\n{error}")
            self.empty_label.show()
            self.table.hide()
            return
        self.last_error = None
        self.empty_label.setStyleSheet(inventory.LIST_STATE_QSS)
        self.table.show()
        self.table.setRowCount(len(self._suppliers))
        for row, supplier in enumerate(self._suppliers):
            for column, value in enumerate((
                supplier.name, supplier.document or "—", supplier.email or "—",
                supplier.phone or "—", supplier.address or "—",
            )):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row, column, item)
            status = QLabel(supplier.status)
            status.setObjectName("statusBadge")
            status.setAlignment(Qt.AlignCenter)
            status.setProperty("status", supplier.status)
            self.table.setCellWidget(row, 5, status)

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(8)
            edit = QPushButton("Editar")
            edit.setObjectName("supplierActionButton")
            edit.setMinimumSize(72, 34)
            edit.clicked.connect(
                lambda _=False, item=supplier: self.open_form(item)
            )
            toggle = QPushButton("Inativar" if supplier.active else "Reativar")
            toggle.setObjectName("supplierActionButton")
            toggle.setMinimumSize(100, 34)
            toggle.clicked.connect(
                lambda _=False, item=supplier: self.toggle_status(item)
            )
            edit.setCursor(Qt.PointingHandCursor)
            toggle.setCursor(Qt.PointingHandCursor)
            action_layout.addWidget(edit)
            action_layout.addWidget(toggle)
            self.table.setCellWidget(row, 6, actions)
            self.table.setRowHeight(row, 56)
        self.empty_label.setText(
            "Nenhum fornecedor encontrado para esta busca."
            if self.search_input.text().strip()
            else "Nenhum fornecedor cadastrado."
        )
        self._filter_table(self.search_input.text())

    def _filter_table(self, text):
        if self.last_error is not None:
            return
        query = (text or "").strip().casefold()
        digits = "".join(char for char in query if char.isdigit())
        visible = 0
        for row, supplier in enumerate(self._suppliers):
            values = (
                supplier.name, supplier.document, supplier.phone, supplier.email,
                supplier.address, supplier.status,
            )
            matches = not query or any(query in value.casefold() for value in values)
            if digits and (
                digits in "".join(c for c in supplier.document if c.isdigit())
                or digits in "".join(c for c in supplier.phone if c.isdigit())
            ):
                matches = True
            status = self.status_filter.currentIndex()
            matches = matches and (status == 0 or supplier.active == (status == 1))
            self.table.setRowHidden(row, not matches)
            visible += int(matches)
        self.empty_label.setText("Nenhum fornecedor corresponde aos filtros." if query or self.status_filter.currentIndex() else "Nenhum fornecedor cadastrado.")
        self.empty_label.setVisible(visible == 0)
        self.result_count.setText(f"{visible} de {len(self._suppliers)} fornecedores")

    def open_form(self, supplier: Supplier | None = None):
        dialog = QDialog(self)
        dialog.setWindowTitle("Novo fornecedor" if supplier is None else "Editar fornecedor")
        dialog.setObjectName("supplierForm")
        dialog.setMinimumWidth(440)
        dialog.setStyleSheet(SUPPLIERS_QSS)
        form = QFormLayout(dialog)
        form.setContentsMargins(24, 24, 24, 24)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        fields = {
            "name": QLineEdit(supplier.name if supplier else ""),
            "document": QLineEdit(supplier.document if supplier else ""),
            "phone": QLineEdit(supplier.phone if supplier else ""),
            "email": QLineEdit(supplier.email if supplier else ""),
            "address": QLineEdit(supplier.address if supplier else ""),
        }
        fields["document"].setPlaceholderText("CPF ou CNPJ (opcional)")
        fields["phone"].setPlaceholderText("(11) 99999-9999")
        fields["email"].setPlaceholderText("contato@empresa.com.br")
        fields["address"].setPlaceholderText("Endereço (opcional)")
        for key, label in (
            ("name", "Nome / razão social"), ("document", "CPF/CNPJ"),
            ("phone", "Telefone"), ("email", "E-mail"), ("address", "Endereço"),
        ):
            form.addRow(label, fields[key])
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Salvar")
        buttons.button(QDialogButtonBox.Save).setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.button(QDialogButtonBox.Cancel).setObjectName("secondaryButton")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return

        payload = SupplierInput(
            supplier_id=supplier.supplier_id if supplier else None,
            name=fields["name"].text(),
            document=fields["document"].text(),
            phone=fields["phone"].text(),
            email=fields["email"].text(),
            address=fields["address"].text(),
            active=supplier.active if supplier else True,
        )
        try:
            if supplier is None:
                self.service.create_supplier(self.session, payload)
            else:
                self.service.update_supplier(self.session, supplier.supplier_id, payload)
        except (ValueError, LookupError) as error:
            self._show_error(str(error))
            return
        except Exception as error:
            self.last_error = error
            self._show_error(f"Não foi possível salvar o fornecedor: {error}")
            return
        self.reload_table()
        self.suppliers_changed.emit()

    def toggle_status(self, supplier: Supplier):
        try:
            self.service.set_active(self.session, supplier.supplier_id, not supplier.active)
        except Exception as error:
            self.last_error = error
            self._show_error(f"Não foi possível alterar o status: {error}")
            return
        self.reload_table()
        self.suppliers_changed.emit()

    @staticmethod
    def _show_error(message):
        QMessageBox.warning(None, "Fornecedor inválido", message)
