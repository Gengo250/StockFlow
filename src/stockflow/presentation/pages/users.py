import qtawesome as qta
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from stockflow.presentation.widgets.user_form import UserForm
from stockflow.presentation.widgets.user_summary import UserSummary
from stockflow.presentation.demo_users import DEMO_USERS, USER_ROLES
from stockflow.presentation.widgets.user_table import ALL_ROLES, UserTable


from stockflow.presentation.styles.users import USERS_QSS


class UsersPage(QWidget):
    """Administração de usuários — tela inteira restrita ao ADMIN.

    `fn_list_company_users` recusa o não-admin, então nem a listagem deveria
    existir fora do ADMIN. Quem decide o acesso é a `MainWindow`, que esconde
    o item do menu e barra a navegação; esta página é a segunda camada, para
    que nenhum caminho residual (duplo clique, sinal, código futuro) entregue
    uma operação administrativa a quem o banco recusaria.
    """

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
        subtitle = QLabel(f"{len(DEMO_USERS)} usuários fictícios · Dados demonstrativos")
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
        # Nasce fechada: a permissão chega depois, por `apply_session`. Abrir
        # habilitada e esperar que alguém desabilite é exatamente o jeito de
        # ficar aberta quando esse alguém não for chamado.
        self.apply_permission(False)

    def _toolbar(self):
        layout = QHBoxLayout()
        layout.setSpacing(10)
        search = QLineEdit()
        search.setPlaceholderText("Buscar por nome ou e-mail...")
        search.setAccessibleName("Buscar usuários")
        search.addAction(qta.icon("fa5s.search", color="#849ABE"), QLineEdit.LeadingPosition)
        layout.addWidget(search, 1)
        role = QComboBox()
        role.addItems([ALL_ROLES, *USER_ROLES])
        role.setAccessibleName("Filtrar por perfil")
        layout.addWidget(role)
        search.textChanged.connect(
            lambda text: self.user_table.filter_users(text, role.currentText())
        )
        role.currentTextChanged.connect(
            lambda text: self.user_table.filter_users(search.text(), text)
        )
        return layout

    def apply_permission(self, pode_gerenciar: bool):
        """Controles visuais do papel atual.

        É só a primeira camada: a recusa que vale é a da navegação, em
        `MainWindow.show_page`, e a do banco em `fn_is_admin`.
        """
        self._pode_gerenciar = pode_gerenciar
        self.new_user_button.setEnabled(pode_gerenciar)
        self.new_user_button.setToolTip(
            "" if pode_gerenciar
            else "Somente administradores podem cadastrar usuários"
        )
        self.user_table.set_actions_enabled(pode_gerenciar)

    def _open_form(self, user=None):
        """Abre o formulário de usuário, se o papel permitir.

        Guardar aqui, e não só no botão, fecha os caminhos que não passam por
        ele — o duplo clique na tabela e qualquer chamada direta ao método.
        Devolve o diálogo aberto, ou `None` quando a abertura é recusada.
        """
        if not self._pode_gerenciar:
            return None
        dialog = UserForm(user, self, pode_gerenciar=True)
        dialog.setStyleSheet(USERS_QSS)
        dialog.exec()
        return dialog
