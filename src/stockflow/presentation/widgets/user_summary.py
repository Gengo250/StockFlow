import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from stockflow.presentation.demo_users import DEMO_USERS, USER_ROLES

# Índice do perfil nas linhas de demo_data:
# (nome, login, departamento, perfil, status, último acesso, cor)
ROLE_INDEX = 3

# Ícone e cor por perfil. Perfil fora do mapa cai no visual neutro, em vez de
# derrubar a tela — a base de demonstração ganha perfis novos com frequência.
ROLE_STYLE = {
    # Papéis reais do banco (`public.user_role`, traduzidos por roles.py).
    "Administrador": ("fa5s.shield-alt", "#8129FF"),
    "Estoque": ("fa5s.boxes", "#00A77A"),
    "Vendedor": ("fa5s.shopping-cart", "#195BFF"),
}
DEFAULT_STYLE = ("fa5s.user", "#60799E")

PLURALS = {
    "Administrador": "Administradores",
    "Estoque": "Estoque",
    "Vendedor": "Vendedores",
}


class UserSummary(QWidget):
    def __init__(self, users=None, parent=None):
        """Um cartão por perfil PRESENTE nas linhas recebidas.

        Os perfis saem dos próprios dados, não de uma lista fixa: uma empresa
        pode não ter ninguém num dos papéis, e um conjunto fixo mostraria
        cartão zerado para perfil que não existe ali.
        """
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(14)
        self.set_users(DEMO_USERS if users is None else users)

    def set_users(self, users):
        """Refaz os cartões para as linhas recebidas.

        Os cartões são recriados, e não atualizados: o conjunto de PERFIS
        muda junto com os dados (o banco tem três papéis, a demonstração tem
        quatro), então não há correspondência um-a-um entre o que está na
        tela e o que chega.
        """
        self.users = tuple(users)
        layout = self._layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        perfis = tuple(dict.fromkeys(user[ROLE_INDEX] for user in self.users)) or USER_ROLES
        for column, role in enumerate(perfis):
            icon, color = ROLE_STYLE.get(role, DEFAULT_STYLE)
            card = QFrame()
            card.setObjectName("summaryCard")
            card.setFixedHeight(174)
            content = QVBoxLayout(card)
            content.setContentsMargins(18, 18, 18, 18)
            content.setSpacing(8)
            badge = QLabel()
            badge.setFixedSize(36, 36)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(f"background: {color}; border-radius: 11px;")
            badge.setPixmap(qta.icon(icon, color="white").pixmap(18, 18))
            number = QLabel(str(sum(user[ROLE_INDEX] == role for user in self.users)))
            number.setStyleSheet(f"color: {color}; font-size: 27px; font-weight: 600;")
            caption = QLabel(PLURALS.get(role, role))
            caption.setObjectName("muted")
            content.addWidget(badge)
            content.addSpacing(4)
            content.addWidget(number)
            content.addWidget(caption)
            content.addStretch()
            layout.addWidget(card, 0, column)
            layout.setColumnStretch(column, 1)
