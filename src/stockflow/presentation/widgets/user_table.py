import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from stockflow.presentation.demo_data import linhas_de_usuarios


# Dados demonstrativos exclusivos da apresentação.
# A tela de Vendas lê a mesma base em demo_data, para que todo usuário
# ativo aqui tenha um cliente associável lá.
DEMO_USERS = linhas_de_usuarios()


class UserTable(QFrame):
    edit_requested = Signal(object)

    venda_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("userTableCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.table = QTableWidget(len(DEMO_USERS), 6)
        self.table.setHorizontalHeaderLabels([
            "Usuário / Login", "Departamento", "Perfil", "Status", "Último acesso", "Ações",
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(64)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setMinimumSectionSize(100)
        for column, width in ((1, 130), (2, 150), (3, 110), (4, 165), (5, 130)):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            self.table.setColumnWidth(column, width)
        for row, user in enumerate(DEMO_USERS):
            name, login, department, role, status, last_access, color = user
            for column, text in enumerate(("", department, "", "", last_access, "")):
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
            role_color = {"Administrador": "#8129FF", "Gerente": "#195BFF", "Financeiro": "#D67B00"}.get(role, "#526785")
            self.table.setCellWidget(row, 2, self._badge(role, role_color))
            status_color = {"Ativo": "#009D73", "Inativo": "#7385A0", "Pendente": "#D67B00"}[status]
            self.table.setCellWidget(row, 3, self._badge(status, status_color))
            actions = QWidget()
            buttons = QHBoxLayout(actions)
            buttons.setContentsMargins(6, 0, 12, 0)
            edit = QPushButton()
            edit.setIcon(qta.icon("fa5s.pen", color="#849ABE"))
            edit.setToolTip(f"Editar {name}")
            edit.setAccessibleName(f"Editar {name}")
            edit.setObjectName("iconButton")
            edit.setFixedSize(30, 30)
            edit.clicked.connect(lambda checked=False, index=row: self._edit(index))

            btn_venda = QPushButton()
            btn_venda.setIcon(qta.icon("fa5s.shopping-cart", color="#849ABE" if status == "Ativo" else "#CBD5E1"))
            btn_venda.setToolTip("Associar a uma venda" if status == "Ativo" else "Cliente inativo (não associável)")
            btn_venda.setObjectName("iconButton")
            btn_venda.setFixedSize(30, 30)
            btn_venda.setEnabled(status == "Ativo") 
            btn_venda.clicked.connect(lambda checked=False, client_name=name: self.venda_requested.emit(client_name))

            toggle = QPushButton()
            toggle.setIcon(qta.icon("fa5s.ban" if status == "Ativo" else "fa5s.check-circle", color="#849ABE"))
            action = "Desativar" if status == "Ativo" else "Ativar"
            toggle.setToolTip(f"{action} usuário — disponível após integração")
            toggle.setAccessibleName(f"{action} {name}")
            toggle.setObjectName("iconButton")
            toggle.setFixedSize(30, 30)
            toggle.setEnabled(False)
            buttons.addWidget(edit)
            buttons.addWidget(btn_venda)
            buttons.addWidget(toggle)
            self.table.setCellWidget(row, 5, actions)
        self.table.cellDoubleClicked.connect(lambda row, column: self._edit(row))
        layout.addWidget(self.table)
        footer = QHBoxLayout()
        footer.setContentsMargins(18, 12, 18, 12)
        total = len(DEMO_USERS)
        count = QLabel(f"{total} de {total} usuários exibidos")
        count.setObjectName("muted")
        footer.addWidget(count)
        footer.addStretch()
        for text in ("Anterior", "1", "Próximo"):
            button = QPushButton(text)
            button.setObjectName("primaryButton" if text == "1" else "secondaryButton")
            button.setEnabled(False)
            footer.addWidget(button)
        layout.addLayout(footer)

    def _edit(self, row):
        self.table.selectRow(row)
        self.edit_requested.emit(DEMO_USERS[row])

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
