"""Página de cadastro, consulta e edição de clientes."""

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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

from stockflow.application.dto.client_input import ClientInput
from stockflow.application.services.client_service import ClientService
from stockflow.domain.entities.client import Client
from stockflow.domain.permissions import can_manage_clients
from stockflow.infrastructure.repositories.demo_client_repository import DemoClientRepository
from stockflow.presentation.demo_data import base_de_clientes
from stockflow.presentation.styles.clients import CLIENTS_QSS
from stockflow.presentation.widgets.client_inputs import (
    ClientDocumentInput,
    ClientPhoneInput,
)


class ClientesPage(QWidget):
    def __init__(self, sales_page=None, clients=None, parent=None, repository=None, session=None):
        super().__init__(parent)
        self.sales_page = sales_page
        self.setObjectName("clientsPage")
        self.setStyleSheet(CLIENTS_QSS)
        self.repository = repository if repository is not None else DemoClientRepository(clients)
        self.service = ClientService(self.repository, session)
        self.session = session
        self._build_ui()
        self.apply_session(session)

    def apply_session(self, session):
        self.session = session
        self.service.session = session
        self.new_client_button.setEnabled(can_manage_clients(session))
        self.reload_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(4)
        title = QLabel("Clientes")
        title.setObjectName("pageTitle")
        heading.addWidget(title)
        subtitle = QLabel("Cadastre, consulte e mantenha os clientes ativos ou inativos.")
        subtitle.setObjectName("muted")
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por nome ou e-mail")
        self.search_input.setAccessibleName("Buscar clientes")
        self.search_input.setMinimumHeight(42)
        self.search_input.addAction(qta.icon("fa5s.search", color="#94A3B8"), QLineEdit.LeadingPosition)
        self.search_input.textChanged.connect(self._filter_table)
        header.addWidget(self.search_input, 2)

        self.new_client_button = QPushButton("Novo Cliente")
        self.new_client_button.setObjectName("primaryButton")
        self.new_client_button.setMinimumHeight(40)
        self.new_client_button.setIcon(qta.icon("fa5s.plus", color="white"))
        self.new_client_button.clicked.connect(lambda: self.open_form())
        header.addWidget(self.new_client_button)
        layout.addLayout(header)

        self.table_card = QFrame()
        self.table_card.setObjectName("clientsTableCard")
        table_layout = QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Nome",
            "Documento",
            "E-mail",
            "Telefone",
            "Status",
            "Ações",
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 210)
        table_layout.addWidget(self.table)
        layout.addWidget(self.table_card)

    def reload_table(self):
        clientes = sorted(self.service.list_clients(), key=lambda c: c.name.casefold())
        self.table.clearContents()
        self.table.setRowCount(len(clientes))
        for row, cliente in enumerate(clientes):
            self.table.setItem(row, 0, QTableWidgetItem(cliente.name))
            self.table.setItem(row, 1, QTableWidgetItem(cliente.document))
            self.table.setItem(row, 2, QTableWidgetItem(cliente.email))
            self.table.setItem(row, 3, QTableWidgetItem(cliente.phone))
            self.table.setRowHeight(row, 48)

            status_label = QLabel(cliente.status)
            status_label.setObjectName("statusBadge")
            status_label.setProperty("data-status", cliente.status)
            status_label.setProperty("status", cliente.status)
            status_label.setAlignment(Qt.AlignCenter)
            status_label.setStyleSheet(
                "QLabel { border-radius: 999px; padding: 6px 10px; font-weight: 600; }"
                + (
                    "QLabel { background: #E4F7EF; color: #0F7B4F; }"
                    if cliente.status == "Ativo"
                    else "QLabel { background: #FBE9E9; color: #8A3B3B; }"
                    if cliente.status == "Inativo"
                    else "QLabel { background: #FDF3DF; color: #8A6A1F; }"
                )
            )
            self.table.setCellWidget(row, 4, status_label)

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(8)
            edit_button = QPushButton("Editar")
            edit_button.setObjectName("clientActionButton")
            edit_button.setMinimumSize(72, 34)
            edit_button.clicked.connect(lambda checked=False, client=cliente: self.open_form(client))
            toggle_button = QPushButton("Inativar" if cliente.active else "Reativar")
            toggle_button.setObjectName("clientActionButton")
            toggle_button.setMinimumSize(100, 34)
            toggle_button.clicked.connect(lambda checked=False, client=cliente: self.toggle_status(client))
            edit_button.setEnabled(can_manage_clients(self.session))
            toggle_button.setEnabled(can_manage_clients(self.session))
            actions_layout.addWidget(edit_button)
            actions_layout.addWidget(toggle_button)
            self.table.setCellWidget(row, 5, actions)
        self._filter_table(self.search_input.text())
        self._sync_sales_page()

    def _sync_sales_page(self):
        if self.sales_page is not None:
            self.sales_page.clientes = [
                {"id": c.client_id, "nome": c.name, "status": c.status}
                for c in self.service.list_clients()
            ]
            self.sales_page.recarregar_clientes_disponiveis()

    def open_form(self, client: Client | None = None):
        if not can_manage_clients(self.session):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Cliente" if client is None else "Editar cliente")
        dialog.setObjectName("clientForm")
        dialog.setMinimumWidth(460)
        dialog.setStyleSheet(CLIENTS_QSS)
        form = QFormLayout(dialog)
        form.setContentsMargins(24, 24, 24, 24)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)

        fields = {
            "name": QLineEdit(client.name if client else ""),
            "document": ClientDocumentInput(client.document if client else ""),
            "email": QLineEdit(client.email if client else ""),
            "phone": ClientPhoneInput(client.phone if client else ""),
            "notes": QLineEdit(client.notes if client else ""),
        }
        if client is not None:
            status = QComboBox()
            status.addItems(["Ativo", "Inativo"])
            status.setCurrentText(client.status)
            fields["status"] = status

        labels = {
            "name": "Nome",
            "document": "Documento",
            "email": "E-mail",
            "phone": "Telefone",
            "notes": "Observações",
            "status": "Status",
        }
        for field, widget in fields.items():
            form.addRow(labels[field], widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_button = buttons.button(QDialogButtonBox.Save)
        save_button.setText("Salvar")
        save_button.setObjectName("primaryButton")
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        cancel_button.setText("Cancelar")
        cancel_button.setObjectName("secondaryButton")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() == QDialog.Accepted:
            payload = ClientInput(
                client_id=client.client_id if client else None,
                name=fields["name"].text(),
                document=fields["document"].text(),
                email=fields["email"].text(),
                phone=fields["phone"].text(),
                notes=fields["notes"].text(),
                active=(fields["status"].currentText() == "Ativo") if client else True,
            )
            try:
                if client is None:
                    self.service.create_client(payload)
                else:
                    self.service.update_client(client.client_id, payload)
                self.reload_table()
            except Exception as error:
                self._show_error(str(error))

    def toggle_status(self, client: Client):
        try:
            self.service.set_active(client.client_id, not client.active)
            self.reload_table()
        except Exception as error:
            self._show_error(str(error))

    def _filter_table(self, text: str):
        filtro = (text or "").strip().casefold()
        for row in range(self.table.rowCount()):
            match = False
            for col in range(5):
                item = self.table.item(row, col)
                if item is None:
                    continue
                if filtro in item.text().casefold():
                    match = True
                    break
            self.table.setRowHidden(row, bool(filtro) and not match)

    @staticmethod
    def _show_error(message: str):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(None, "Cliente inválido", message)
