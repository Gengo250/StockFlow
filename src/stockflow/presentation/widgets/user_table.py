import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QLabel, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


from stockflow.presentation.demo_users import DEMO_USERS



class UserTable(QFrame):
    edit_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("userTableCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.table = QTableWidget(len(DEMO_USERS), 3)
        self.table.setHorizontalHeaderLabels(["Usuário", "Perfil", "Ações"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(64)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setMinimumSectionSize(100)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 100)
        for row, user in enumerate(DEMO_USERS):
            name, email, role = user
            color = {"Administrador": "#8129FF", "Estoquista": "#195BFF", "Financeiro": "#E78A00"}[role]
            identity_item = QTableWidgetItem()
            identity_item.setData(Qt.AccessibleTextRole, f"{name}, {email}")
            self.table.setItem(row, 0, identity_item)
            role_item = QTableWidgetItem()
            role_item.setData(Qt.AccessibleTextRole, role)
            self.table.setItem(row, 1, role_item)
            self.table.setItem(row, 2, QTableWidgetItem())
            self.table.setCellWidget(row, 0, self._identity(name, email, color))
            self.table.setCellWidget(row, 1, self._role_badge(role, color))
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(12, 0, 12, 0)
            edit = QPushButton()
            edit.setObjectName("iconButton")
            edit.setFixedSize(32, 32)
            edit.setIcon(qta.icon("fa5s.pen", color="#849ABE"))
            edit.setToolTip(f"Editar {name}")
            edit.setAccessibleName(f"Editar {name}")
            edit.clicked.connect(lambda checked=False, index=row: self._edit(index))
            actions_layout.addWidget(edit)
            actions_layout.addStretch()
            self.table.setCellWidget(row, 2, actions)
        self.table.cellDoubleClicked.connect(lambda row, column: self._edit(row))
        layout.addWidget(self.table)
        self.count = QLabel()
        self.count.setObjectName("muted")
        self.count.setContentsMargins(18, 12, 18, 12)
        layout.addWidget(self.count)
        self.filter_users()

    def filter_users(self, query="", role="Todos os perfis"):
        query = query.strip().casefold()
        visible = 0
        for row, (name, email, profile) in enumerate(DEMO_USERS):
            match = (query in f"{name} {email}".casefold()
                     and (role == "Todos os perfis" or profile == role))
            self.table.setRowHidden(row, not match)
            visible += match
        self.count.setText(f"{visible} de {len(DEMO_USERS)} usuários exibidos")

    def _edit(self, row):
        self.table.selectRow(row)
        self.edit_requested.emit(DEMO_USERS[row])

    @staticmethod
    def _identity(name, email, color):
        container = QWidget()
        container.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(18, 8, 12, 8)
        layout.setSpacing(12)
        avatar = QLabel("".join(part[0] for part in name.split()[:2]))
        avatar.setFixedSize(34, 34)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(f"background: {color}; color: white; border-radius: 11px; font-size: 11px; font-weight: 600;")
        layout.addWidget(avatar)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        name_label = QLabel(name)
        name_label.setStyleSheet("color: #1E293B; font-size: 12px; font-weight: 600;")
        email_label = QLabel(email)
        email_label.setStyleSheet("color: #849ABE; font-size: 11px;")
        texts.addWidget(name_label)
        texts.addWidget(email_label)
        layout.addLayout(texts, 1)
        return container

    @staticmethod
    def _role_badge(role, color):
        container = QWidget()
        container.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 0, 12, 0)
        badge = QLabel(role)
        badge.setFixedHeight(24)
        badge.setStyleSheet(f"color: {color}; background: #F7FAFF; border: 1px solid #DBE5F5; border-radius: 9px; padding: 3px 9px; font-size: 11px;")
        layout.addWidget(badge)
        layout.addStretch()
        return container
