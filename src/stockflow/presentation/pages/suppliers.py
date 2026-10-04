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
        layout.setSpacing(16)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(4)
        title = QLabel("Fornecedores")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Cadastre, consulte e mantenha fornecedores ativos ou inativos.")
        subtitle.setObjectName("muted")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Buscar por nome, CPF/CNPJ ou informações de contato"
        )
        self.search_input.setAccessibleName("Buscar fornecedores")
        self.search_input.setMinimumHeight(42)
        self.search_input.addAction(
            qta.icon("fa5s.search", color="#94A3B8"), QLineEdit.LeadingPosition
        )
        self.search_input.textChanged.connect(self._filter_table)
        header.addWidget(self.search_input, 2)
        self.new_supplier_button = QPushButton("Novo fornecedor")
        self.new_supplier_button.setObjectName("primaryButton")
        self.new_supplier_button.setMinimumHeight(40)
        self.new_supplier_button.setIcon(qta.icon("fa5s.plus", color="white"))
        self.new_supplier_button.clicked.connect(lambda: self.open_form())
        header.addWidget(self.new_supplier_button)
        layout.addLayout(header)

        self.table_card = QFrame()
        self.table_card.setObjectName("suppliersTableCard")
        table_layout = QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
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
        self.table.verticalHeader().hide()
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.Stretch)
        header_view.setSectionResizeMode(5, QHeaderView.Fixed)
        header_view.setSectionResizeMode(6, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 210)
        table_layout.addWidget(self.table)
        layout.addWidget(self.table_card, 1)
        self.empty_label = QLabel("Nenhum fornecedor cadastrado.")
        self.empty_label.setObjectName("muted")
        self.empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_label)
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
            self.empty_label.setText(f"Não foi possível carregar fornecedores.\n{error}")
            self.empty_label.show()
            self.table.hide()
            return
        self.last_error = None
        self.table.show()
        self.table.setRowCount(len(self._suppliers))
        for row, supplier in enumerate(self._suppliers):
            for column, value in enumerate((
                supplier.name, supplier.document or "—", supplier.email or "—",
                supplier.phone or "—", supplier.address or "—",
            )):
                self.table.setItem(row, column, QTableWidgetItem(value))
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
            action_layout.addWidget(edit)
            action_layout.addWidget(toggle)
            self.table.setCellWidget(row, 6, actions)
            self.table.setRowHeight(row, 48)
        self.empty_label.setText(
            "Nenhum fornecedor encontrado para esta busca."
            if self.search_input.text().strip()
            else "Nenhum fornecedor cadastrado."
        )
        self._filter_table(self.search_input.text())

    def _filter_table(self, text):
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
            self.table.setRowHidden(row, not matches)
            visible += int(matches)
        self.empty_label.setVisible(visible == 0)

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
