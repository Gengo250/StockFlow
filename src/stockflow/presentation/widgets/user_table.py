import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

ALL_ROLES = "Todos os perfis"
ACTIONS_COLUMN = 5

from stockflow.presentation.demo_users import DEMO_USERS
from stockflow.presentation.demo_data import linhas_de_usuarios


class UserTable(QFrame):
    edit_requested = Signal(object)
    status_change_requested = Signal(object, bool)
    venda_requested = Signal(str)

    def __init__(self, users=None, parent=None):
        super().__init__(parent)
        self.users = tuple(linhas_de_usuarios() if users is None else users)
        self._actions_enabled = False
        self._search_text = ""
        self._role_filter = ALL_ROLES
        self.setObjectName("userTableCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Usuário / Login", "Departamento", "Perfil", "Status",
            "Último acesso", "Ações",
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(64)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setMinimumSectionSize(90)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in ((1, 125), (2, 135), (3, 105), (4, 165)):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            self.table.setColumnWidth(column, width)
        # A última seção precisa preencher a largura restante. Sem isso o
        # viewport do cabeçalho fica com a paleta padrão escura à direita.
        header.setSectionResizeMode(ACTIONS_COLUMN, QHeaderView.Stretch)
        self.table.setColumnWidth(ACTIONS_COLUMN, 255)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setAlternatingRowColors(False)

        layout.addWidget(self.table)
        footer = QHBoxLayout()
        footer.setContentsMargins(18, 12, 18, 12)
        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        footer.addWidget(self.count_label)
        footer.addStretch()
        for text in ("Anterior", "1", "Próximo"):
            button = QPushButton(text)
            button.setObjectName("primaryButton" if text == "1" else "secondaryButton")
            button.setEnabled(False)
            footer.addWidget(button)
        layout.addLayout(footer)
        self.table.cellDoubleClicked.connect(self._edit_double_clicked)
        self.set_users(self.users)

    def set_users(self, users) -> None:
        """Repovoa a mesma tabela com linhas de demonstração ou do diretório."""
        self.users = tuple(users)
        self._render_users()

    def _render_users(self) -> None:
        self.table.setRowCount(len(self.users))

        for row, user in enumerate(self.users):
            name, login, department, role, status, last_access, color = user[:7]
            for column, text in (
                (1, department), (4, last_access),
            ):
                self.table.setItem(row, column, QTableWidgetItem(text))
            identity = QWidget()
            identity_layout = QHBoxLayout(identity)
            identity_layout.setContentsMargins(16, 6, 12, 6)
            avatar = QLabel("".join(part[0] for part in name.split()[:2]))
            avatar.setAlignment(Qt.AlignCenter)
            avatar.setFixedSize(34, 34)
            avatar.setStyleSheet(f"background: {color}; color: white; border-radius: 11px; font-weight: 600;")
            texts = QVBoxLayout()
            texts.setSpacing(3)
            identity.setToolTip(f"{name}\n{login}")
            name_label = QLabel(name)
            name_label.setStyleSheet("color: #1E293B; font-weight: 600;")
            login_label = QLabel(login)
            login_label.setStyleSheet("color: #849ABE; font-size: 11px;")
            texts.addWidget(name_label)
            texts.addWidget(login_label)
            identity_layout.addWidget(avatar)
            identity_layout.addLayout(texts)
            identity_layout.addStretch()
            identity.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.table.setCellWidget(row, 0, identity)
            role_color = {"Administrador": "#8129FF", "Estoque": "#00A77A", "Vendedor": "#195BFF"}.get(role, "#526785")
            self.table.setCellWidget(row, 2, self._badge(role, role_color))
            status_color = {"Ativo": "#009D73", "Inativo": "#7385A0", "Pendente": "#D67B00"}.get(status, "#7385A0")
            self.table.setCellWidget(row, 3, self._badge(status, status_color))

            user_id = getattr(user, "user_id", None)
            actions = self.table.cellWidget(row, ACTIONS_COLUMN)
            if actions is None:
                actions = QWidget()
                buttons = QHBoxLayout(actions)
                buttons.setContentsMargins(6, 0, 8, 0)
                buttons.setSpacing(2)
                edit = QPushButton()
                edit.setObjectName("iconButton")
                edit.setFixedSize(30, 30)
                edit.clicked.connect(self._edit_button_clicked)
                venda = QPushButton()
                venda.setObjectName("iconButton")
                venda.setFixedSize(30, 30)
                venda.clicked.connect(self._sale_button_clicked)
                toggle = QPushButton()
                toggle.setObjectName("secondaryButton")
                toggle.setFixedHeight(30)
                toggle.clicked.connect(self._status_button_clicked)
                buttons.addWidget(edit)
                buttons.addWidget(venda)
                buttons.addWidget(toggle)
                self.table.setCellWidget(row, ACTIONS_COLUMN, actions)
            else:
                buttons = actions.layout()
                edit = buttons.itemAt(0).widget()
                venda = buttons.itemAt(1).widget()
                toggle = buttons.itemAt(2).widget()

            edit.setIcon(qta.icon("fa5s.pen", color="#849ABE"))
            edit.setToolTip(f"Editar {name}")
            edit.setAccessibleName(f"Editar {name}")
            edit.user_row = row
            venda.setIcon(qta.icon("fa5s.shopping-cart", color="#849ABE"))
            venda.setToolTip(f"Abrir vendas para {name}")
            venda.setAccessibleName(f"Abrir vendas para {name}")
            venda.customer_name = name
            venda.setEnabled(status == "Ativo")
            action = "Desativar" if status == "Ativo" else "Ativar"
            toggle.setIcon(qta.icon(
                "fa5s.ban" if status == "Ativo" else "fa5s.check-circle",
                color="#849ABE",
            ))
            toggle.setText(action)
            toggle.setToolTip(f"{action} usuário")
            toggle.setAccessibleName(f"{action} {name}")
            toggle.user_id = user_id
            toggle.user_active = status == "Ativo"
            toggle.setEnabled(bool(user_id))

        self.set_actions_enabled(self._actions_enabled)
        self._apply_filters()

    def _action_buttons(self, index):
        actions = self.table.cellWidget(index, ACTIONS_COLUMN)
        if actions is None:
            return None
        return tuple(
            actions.layout().itemAt(position).widget()
            for position in range(3)
        )

    @property
    def edit_buttons(self):
        return [
            buttons[0] for row in range(self.table.rowCount())
            if (buttons := self._action_buttons(row)) is not None
        ]

    @property
    def venda_buttons(self):
        return [
            buttons[1] for row in range(self.table.rowCount())
            if (buttons := self._action_buttons(row)) is not None
        ]

    @property
    def status_buttons(self):
        return [
            buttons[2] for row in range(self.table.rowCount())
            if (buttons := self._action_buttons(row)) is not None
        ]

    def _edit_double_clicked(self, row, _column) -> None:
        self._edit(row)

    def _edit_button_clicked(self) -> None:
        self._edit(self.sender().user_row)

    def _sale_button_clicked(self) -> None:
        self.venda_requested.emit(self.sender().customer_name)

    def _status_button_clicked(self) -> None:
        button = self.sender()
        if self._actions_enabled and button.user_id:
            self.status_change_requested.emit(
                str(button.user_id), not button.user_active
            )

    def _edit(self, row):
        if not self._actions_enabled or row < 0 or row >= len(self.users):
            return
        self.table.selectRow(row)
        self.edit_requested.emit(self.users[row])

    def set_actions_enabled(self, enabled: bool) -> None:
        """Habilita ou desabilita os botões/ações de gerenciamento de usuários."""
        self._actions_enabled = enabled
        for button in self.edit_buttons:
            button.setEnabled(enabled)
        for button, user in zip(self.status_buttons, self.users):
            button.setEnabled(enabled and bool(getattr(user, "user_id", None)))

    def filter_users(self, search="", role=ALL_ROLES) -> None:
        self._search_text = search.strip().casefold()
        self._role_filter = role
        self._apply_filters()

    def _apply_filters(self) -> None:
        visible = 0
        for row, user in enumerate(self.users):
            search_match = (
                not self._search_text
                or any(self._search_text in str(value).casefold() for value in user[:5])
            )
            role_match = self._role_filter == ALL_ROLES or user[3] == self._role_filter
            hidden = not (search_match and role_match)
            self.table.setRowHidden(row, hidden)
            visible += not hidden
        self.count_label.setText(
            f"{visible} de {len(self.users)} usuários exibidos"
        )

    @staticmethod
    def _badge(text, color):
        container = QWidget()
        container.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(8, 0, 8, 0)
        label = QLabel(text)
        label.setFixedHeight(24)
        label.setStyleSheet(f"color: {color}; background: #F7FAFF; border: 1px solid #DBE5F5; border-radius: 9px; padding: 3px 9px; font-size: 11px;")
        layout.addWidget(label)
        layout.addStretch()
        return container
