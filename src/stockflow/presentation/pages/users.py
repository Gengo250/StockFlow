import qtawesome as qta
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from stockflow.presentation.widgets.user_form import UserForm
from stockflow.presentation.widgets.user_summary import UserSummary
from stockflow.presentation.widgets.user_table import UserTable


USERS_QSS = """
    QWidget#usersPage, QDialog#userForm { background: #F0F5FF; }
    QWidget#usersPage QLabel, QDialog#userForm QLabel {
        background: transparent; color: #263650; font-size: 13px;
    }
    QWidget#usersPage QLabel#pageTitle, QDialog#userForm QLabel#pageTitle {
        color: #0F172A; font-size: 24px; font-weight: 700;
    }
    QWidget#usersPage QLabel#muted, QDialog#userForm QLabel#muted {
        color: #6980A5; font-size: 12px;
    }
    QFrame#summaryCard, QFrame#userTableCard {
        background: white; border: 1px solid #D7E5FF; border-radius: 14px;
    }
    QLineEdit, QComboBox {
        background: white; color: #475569; border: 1px solid #D7E5FF;
        border-radius: 10px; padding: 10px 12px; font-size: 13px;
    }
    QLineEdit:focus, QComboBox:focus { border: 1px solid #195BFF; }
    QComboBox::drop-down { border: none; width: 24px; }
    QComboBox QAbstractItemView { background: white; color: #263650; selection-background-color: #DBEAFE; }
    QPushButton { padding: 10px 14px; border-radius: 10px; font-size: 13px; }
    QPushButton#primaryButton, QPushButton:checked {
        background: #195BFF; color: white; border: 1px solid #195BFF;
    }
    QPushButton#primaryButton:hover { background: #154EDD; }
    QPushButton#secondaryButton {
        background: white; color: #475569; border: 1px solid #D7E5FF;
    }
    QPushButton#secondaryButton:checked { background: #195BFF; color: white; }
    QPushButton#secondaryButton:hover { border-color: #90B5FF; }
    QPushButton#primaryButton:disabled { background: #90B5FF; border-color: #90B5FF; }
    QPushButton#secondaryButton:disabled { color: #8A9DBA; }
    QPushButton#iconButton { background: transparent; border: none; padding: 4px; }
    QPushButton#iconButton:hover { background: #EAF1FF; }
    QTableWidget { background: white; color: #6980A5; border: none; font-size: 12px; }
    QTableWidget::item { padding: 10px; border-bottom: 1px solid #EDF3FF; }
    QTableWidget::item:selected { background: #E7EFFF; color: #243F70; }
    QHeaderView::section {
        background: #F4F8FF; color: #60799E; border: none;
        border-bottom: 1px solid #D7E5FF; padding: 13px 12px; font-size: 11px;
    }
"""


class UsersPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("usersPage")
        self.setStyleSheet(USERS_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 24, 22, 22)
        layout.setSpacing(22)
        header = QHBoxLayout()
        headings = QVBoxLayout()
        headings.setSpacing(5)
        title = QLabel("Administração de Usuários")
        title.setObjectName("pageTitle")
        subtitle = QLabel("8 usuários cadastrados no sistema")
        subtitle.setObjectName("muted")
        headings.addWidget(title)
        headings.addWidget(subtitle)
        header.addLayout(headings)
        header.addStretch()
        self.new_user_button = QPushButton("Novo Usuário")
        self.new_user_button.setObjectName("primaryButton")
        self.new_user_button.setIcon(qta.icon("fa5s.plus", color="white"))
        self.new_user_button.clicked.connect(lambda: self._open_form())
        header.addWidget(self.new_user_button)
        layout.addLayout(header)
        layout.addWidget(UserSummary())
        layout.addLayout(self._toolbar())
        self.user_table = UserTable()
        self.user_table.edit_requested.connect(self._open_form)
        layout.addWidget(self.user_table, 1)

    def _toolbar(self):
        layout = QHBoxLayout()
        layout.setSpacing(10)
        search = QLineEdit()
        search.setPlaceholderText("Buscar por nome, login ou ID...")
        search.setAccessibleName("Buscar usuários")
        search.addAction(qta.icon("fa5s.search", color="#849ABE"), QLineEdit.LeadingPosition)
        layout.addWidget(search, 1)
        role = QComboBox()
        role.addItems(["Todos os perfis", "Administrador", "Gerente", "Operador", "Financeiro"])
        role.setAccessibleName("Filtrar por perfil")
        layout.addWidget(role)
        self.filter_group = QButtonGroup(self)
        for index, text in enumerate(("Todos", "Ativos", "Inativos", "Pendentes")):
            button = QPushButton(text)
            button.setObjectName("secondaryButton")
            button.setCheckable(True)
            button.setChecked(index == 0)
            self.filter_group.addButton(button)
            layout.addWidget(button)
        return layout

    def _open_form(self, user=None):
        dialog = UserForm(user, self)
        dialog.setStyleSheet(USERS_QSS)
        dialog.exec()
