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
    "Administrador": ("fa5s.shield-alt", "#8129FF"),
    "Gerente": ("fa5s.user-tie", "#195BFF"),
    "Operador": ("fa5s.boxes", "#00A77A"),
    "Financeiro": ("fa5s.wallet", "#FF9500"),
}
DEFAULT_STYLE = ("fa5s.user", "#60799E")

PLURALS = {
    "Administrador": "Administradores",
    "Gerente": "Gerentes",
    "Operador": "Operadores",
    "Financeiro": "Financeiro",
}


class UserSummary(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        for column, role in enumerate(USER_ROLES):
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
            number = QLabel(str(sum(user[ROLE_INDEX] == role for user in DEMO_USERS)))
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
