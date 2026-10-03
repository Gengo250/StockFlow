import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QLabel, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from stockflow.presentation.demo_data import linhas_de_usuarios


# Dados demonstrativos exclusivos da apresentação.
# A tela de Vendas lê a mesma base em demo_data, para que todo usuário
# ativo aqui tenha um cliente associável lá.
#
# Contrato de cada linha:
# (nome, login, departamento, perfil, status, último acesso, cor)
DEMO_USERS = linhas_de_usuarios()

COLUMNS = ("Usuário", "Departamento", "Perfil", "Status", "Último acesso", "Ações")
ACTIONS_COLUMN = len(COLUMNS) - 1

# Entrada neutra do filtro de perfil: equivale a "não filtrar".
ALL_ROLES = "Todos os perfis"

STATUS_COLORS = {
    "Ativo": ("#0F7B4F", "#E4F7EF"),
    "Inativo": ("#8A3B3B", "#FBE9E9"),
    "Pendente": ("#8A6A1F", "#FDF3DF"),
}


class UserTable(QFrame):
    edit_requested = Signal(object)

    venda_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("userTableCard")
        # Botões de editar de cada linha. Eles só existem dentro de
        # cellWidget, e sem esta lista aplicar a permissão exigiria varrer a
        # tabela por índice de coluna — qualquer mudança de layout quebraria
        # o controle em silêncio. Mesmo papel de `StockTable.edit_buttons`.
        self.edit_buttons = []
        # Última permissão aplicada, guardada no widget e não só em quem
        # chama: um QPushButton nasce habilitado, então qualquer caminho que
        # venha a recriar as linhas precisa reaplicar o estado (foi esse o
        # bug da StockTable). Hoje `filter_users` apenas esconde linhas e os
        # botões sobrevivem, mas a memória fica aqui para que um futuro
        # repovoamento não devolva "Editar" a quem não é ADMIN.
        self._actions_enabled = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.table = QTableWidget(len(DEMO_USERS), len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
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
        header.setSectionResizeMode(ACTIONS_COLUMN, QHeaderView.Fixed)
        self.table.setColumnWidth(ACTIONS_COLUMN, 120)
        for row, user in enumerate(DEMO_USERS):
            # A cor vem da própria linha. O mapa perfil -> cor que existia aqui
            # só conhecia três perfis e levantava KeyError em "Gerente" e
            # "Operador", derrubando a janela principal durante a construção.
            name, login, department, role, status, last_access, color = user
            identity_item = QTableWidgetItem()
            identity_item.setData(Qt.AccessibleTextRole, f"{name}, {login}")
            self.table.setItem(row, 0, identity_item)
            self.table.setCellWidget(row, 0, self._identity(name, login, color))
            for column, text in ((1, department), (2, role), (3, status), (4, last_access)):
                item = QTableWidgetItem()
                item.setData(Qt.AccessibleTextRole, text)
                self.table.setItem(row, column, item)
            self.table.setCellWidget(row, 1, self._plain(department))
            self.table.setCellWidget(row, 2, self._role_badge(role, color))
            self.table.setCellWidget(row, 3, self._status_badge(status))
            self.table.setCellWidget(row, 4, self._plain(last_access))
            self.table.setItem(row, ACTIONS_COLUMN, QTableWidgetItem())
            self.table.setCellWidget(row, ACTIONS_COLUMN, self._actions(row, name, status))
        self.table.cellDoubleClicked.connect(lambda row, column: self._edit(row))
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
        self._update_count()

    def _actions(self, row, name, status):
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(12, 0, 12, 0)
        actions_layout.setSpacing(4)
        edit = QPushButton()
        edit.setObjectName("iconButton")
        edit.setFixedSize(32, 32)
        edit.setIcon(qta.icon("fa5s.pen", color="#849ABE"))
        edit.setToolTip(f"Editar {name}")
        edit.setAccessibleName(f"Editar {name}")
        edit.clicked.connect(lambda checked=False, index=row: self._edit(index))
        # Editar usuário é operação de ADMIN (`fn_update_company_user`), então
        # entra no controle de permissão.
        edit.setEnabled(self._actions_enabled)
        self.edit_buttons.append(edit)
        actions_layout.addWidget(edit)
        venda = QPushButton()
        venda.setObjectName("iconButton")
        venda.setFixedSize(32, 32)
        venda.setIcon(qta.icon("fa5s.shopping-cart", color="#849ABE"))
        # Só cliente ativo existe na base de Vendas. Habilitar o botão para
        # inativo levava a uma associação que falhava em silêncio.
        venda.setEnabled(status == "Ativo")
        venda.setToolTip(
            f"Registrar venda para {name}" if status == "Ativo"
            else f"{name} está {status.lower()} e não pode ser associado a uma venda"
        )
        venda.setAccessibleName(f"Registrar venda para {name}")
        venda.clicked.connect(lambda checked=False, cliente=name: self.venda_requested.emit(cliente))
        actions_layout.addWidget(venda)
        actions_layout.addStretch()
        return actions

    def set_actions_enabled(self, enabled: bool):
        """Liga/desliga as ações de administração de usuário da tabela.

        O botão de carrinho fica de fora de propósito: registrar venda para
        um cliente não é gerenciar usuário, e ele já tem a sua própria regra
        (só cliente ativo). Aqui vale `fn_is_admin`, que governa editar.
        """
        self._actions_enabled = enabled
        for button in self.edit_buttons:
            button.setEnabled(enabled)

    def filter_users(self, text="", role=""):
        """Esconde as linhas que não casam com a busca e com o perfil.

        Chamada pelos campos da tela de Usuários, que estavam ligados a um
        método inexistente: digitar na busca derrubava a aplicação.
        """
        query = (text or "").strip().casefold()
        wanted = (role or "").strip()
        if wanted == ALL_ROLES:
            wanted = ""
        for row, user in enumerate(DEMO_USERS):
            name, login, department, user_role = user[0], user[1], user[2], user[3]
            haystack = f"{name} {login} {department}".casefold()
            matches = (not query or query in haystack) and (not wanted or user_role == wanted)
            self.table.setRowHidden(row, not matches)
        self._update_count()

    def _update_count(self):
        shown = sum(not self.table.isRowHidden(row) for row in range(len(DEMO_USERS)))
        self.count_label.setText(f"{shown} de {len(DEMO_USERS)} usuários exibidos")

    def _edit(self, row):
        """Pede a edição da linha. Silencioso quando o papel não pode editar.

        O duplo clique na linha chega aqui SEM passar pelo botão de editar:
        desabilitar o botão sozinho deixaria a edição a um clique duplo de
        distância para quem não é ADMIN.
        """
        if not self._actions_enabled:
            return
        self.table.selectRow(row)
        self.edit_requested.emit(DEMO_USERS[row])

    @staticmethod
    def _plain(text):
        container = QWidget()
        container.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 0, 12, 0)
        value = QLabel(text)
        value.setStyleSheet("color: #60799E; font-size: 12px;")
        layout.addWidget(value)
        layout.addStretch()
        return container

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

    @staticmethod
    def _status_badge(status):
        container = QWidget()
        container.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 0, 12, 0)
        foreground, background = STATUS_COLORS.get(status, ("#60799E", "#F1F5FB"))
        badge = QLabel(status)
        badge.setFixedHeight(24)
        badge.setStyleSheet(f"color: {foreground}; background: {background}; border-radius: 9px; padding: 3px 9px; font-size: 11px; font-weight: 600;")
        layout.addWidget(badge)
        layout.addStretch()
        return container
