import qtawesome as qta
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from stockflow.presentation.widgets.user_form import UserForm
from stockflow.presentation.widgets.user_summary import UserSummary
from stockflow.presentation.demo_data import linhas_de_usuarios
from stockflow.presentation.demo_users import USER_ROLES
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

    def __init__(self, users=None):
        """Tela sobre as linhas recebidas; sem elas, cai na demonstração."""
        super().__init__()
        self.users = tuple(linhas_de_usuarios() if users is None else users)
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
        # O subtítulo diz a ORIGEM dos dados. Deixar "Dados demonstrativos"
        # fixo faria a tela ligada ao banco continuar se anunciando como
        # fictícia — e foi exatamente esse rótulo que explicou por que um
        # usuário real não aparecia aqui.
        self.subtitle = QLabel()
        self.subtitle.setObjectName("muted")
        subtitle = self.subtitle
        self._atualizar_subtitulo(users is not None)
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
        self.summary = UserSummary(self.users)
        layout.addWidget(self.summary)
        layout.addLayout(self._toolbar())
        self.user_table = UserTable(self.users)
        self.user_table.edit_requested.connect(self._open_form)
        layout.addWidget(self.user_table, 1)
        # Nasce fechada: a permissão chega depois, por `apply_session`. Abrir
        # habilitada e esperar que alguém desabilite é exatamente o jeito de
        # ficar aberta quando esse alguém não for chamado.
        self.apply_permission(False)

    def load_users(self, users, from_database=True):
        """Troca a lista exibida pelas linhas recebidas (vindas do banco).

        Existe porque a listagem é restrita ao ADMIN: `fn_list_company_users`
        recusa qualquer outro papel. Buscar no banco durante a construção da
        `MainWindow` faria a janela de um SELLER morrer montando uma tela que
        ele nem pode abrir — por isso a página nasce com a demonstração e só
        troca quando alguém com permissão navega até aqui. `from_database`
        mantém correto o rótulo de origem após uma atualização da demonstração.
        """
        self.users = tuple(users)
        self.user_table.set_users(self.users)
        self.summary.set_users(self.users)
        self._atualizar_perfis_do_filtro()
        self._atualizar_subtitulo(from_database)

    def _atualizar_perfis_do_filtro(self):
        atual = self.role_filter.currentText()
        self.role_filter.blockSignals(True)
        self.role_filter.clear()
        self.role_filter.addItems([ALL_ROLES, *self._perfis()])
        # Preserva a escolha quando ela ainda existe; senão volta ao neutro,
        # em vez de deixar a tabela filtrada por um perfil que sumiu da lista.
        indice = self.role_filter.findText(atual)
        self.role_filter.setCurrentIndex(indice if indice >= 0 else 0)
        self.role_filter.blockSignals(False)
        self.user_table.filter_users(self.search_input.text(), self.role_filter.currentText())

    def _perfis(self):
        """Perfis presentes nos dados, não a lista fixa da demonstração."""
        return tuple(dict.fromkeys(user[3] for user in self.users)) or USER_ROLES

    def _atualizar_subtitulo(self, do_banco: bool):
        origem = "Dados da empresa" if do_banco else "Dados demonstrativos"
        plural = "usuário" if len(self.users) == 1 else "usuários"
        self.subtitle.setText(f"{len(self.users)} {plural} · {origem}")

    def _toolbar(self):
        layout = QHBoxLayout()
        layout.setSpacing(10)
        # Guardados como atributo: `load_users` precisa alcançá-los para
        # reconstruir a lista de perfis e reaplicar o filtro atual.
        self.search_input = search = QLineEdit()
        search.setPlaceholderText("Buscar por nome ou e-mail...")
        search.setAccessibleName("Buscar usuários")
        search.addAction(qta.icon("fa5s.search", color="#849ABE"), QLineEdit.LeadingPosition)
        layout.addWidget(search, 1)
        self.role_filter = role = QComboBox()
        # Perfis presentes nos dados, não a lista fixa da demonstração: filtrar
        # por um perfil que ninguém tem devolve tabela vazia sem explicação.
        role.addItems([ALL_ROLES, *self._perfis()])
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
