import qtawesome as qta

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton

from stockflow.presentation.roles import iniciais, rotulo_de_papel
from stockflow.presentation.styles import theme


class TopBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(52)
        self.setStyleSheet(theme.TOP_BAR_QSS)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(18)
        layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setObjectName("quickSearch")
        self.search_input.setPlaceholderText("Busca rápida...")
        self.search_input.setAccessibleName("Busca rápida")
        self.search_input.setToolTip("Busca rápida — integração em breve")
        self.search_input.setFixedHeight(32)
        self.search_input.setMinimumWidth(120)
        self.search_input.setMaximumWidth(204)
        self.search_input.addAction(
            qta.icon("fa5s.search", color="#8BA1BF"),
            QLineEdit.ActionPosition.LeadingPosition,
        )

        self.notifications_button = QToolButton()
        self.notifications_button.setObjectName("notificationsButton")
        self.notifications_button.setAccessibleName("Notificações")
        self.notifications_button.setToolTip("Notificações — integração em breve")
        self.notifications_button.setIcon(qta.icon("fa5.bell", color="#8292AD"))
        self.notifications_button.setIconSize(QSize(18, 18))
        self.notifications_button.setFixedSize(26, 32)

        self.avatar = QLabel("US")
        self.avatar.setObjectName("topBarAvatar")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFixedSize(30, 30)
        self.avatar.setToolTip("Usuário · Administrador")
        self.avatar.setAccessibleName("Perfil do usuário")

        layout.addWidget(self.search_input)
        layout.addWidget(self.notifications_button)
        layout.addWidget(self.avatar)

    def set_user(self, session=None):
        """Avatar e tooltip do usuário logado; sem sessão, o rótulo genérico."""
        nome = getattr(session, "name", None) or "Usuário"
        papel = rotulo_de_papel(getattr(session, "role", None)) if session else "Administrador"
        self.avatar.setText(iniciais(nome))
        self.avatar.setToolTip(f"{nome} · {papel}")
