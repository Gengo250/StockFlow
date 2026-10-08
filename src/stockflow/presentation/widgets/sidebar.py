import qtawesome as qta

from PySide6.QtWidgets import (
    QFrame,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
)

from PySide6.QtCore import Qt, QSize, Signal

from stockflow.presentation.styles import theme
from stockflow.presentation.widgets.menu_button import create_menu_button


MENU_ITEMS = [
    ("dashboard", "Dashboard", "fa5s.home"),
    ("estoque", "Estoque", "fa5s.cube"),
    ("movimentacoes", "Movimentações", "fa5s.exchange-alt"),
    ("vendas", "Vendas", "fa5s.chart-bar"),
    ("produtos", "Produtos", "fa5s.box"),
    ("relatorios", "Relatórios", "fa5s.file-alt"),
]

SYSTEM_ITEMS = [
    ("usuarios", "Usuários", "fa5s.users"),
    ("configuracoes", "Configurações", "fa5s.cog"),
]

DEFAULT_KEY = "dashboard"


class Sidebar(QFrame):

    page_requested = Signal(str)

    def __init__(self):
        super().__init__()

        self.setFixedWidth(240)

        self.setStyleSheet(theme.SIDEBAR_QSS)

        self.buttons = {}

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            12,
            18,
            12,
            16
        )

        layout.setSpacing(6)

        layout.addWidget(self._create_logo())

        layout.addWidget(self._create_divider())
        layout.addSpacing(10)

        layout.addWidget(self._create_section_title("MENU PRINCIPAL"))
        layout.addSpacing(4)

        for key, label, icon in MENU_ITEMS:
            layout.addWidget(
                self._create_item(key, label, icon)
            )

        layout.addSpacing(8)
        layout.addWidget(self._create_divider())
        layout.addSpacing(10)

        layout.addWidget(self._create_section_title("SISTEMA"))
        layout.addSpacing(4)

        for key, label, icon in SYSTEM_ITEMS:
            layout.addWidget(
                self._create_item(key, label, icon)
            )

        layout.addStretch()

        layout.addWidget(self._create_divider())
        layout.addSpacing(10)

        layout.addWidget(self._create_user_footer())

    # ======================================================
    # ITENS DO MENU
    # ======================================================

    def _create_item(self, key, label, icon):

        button = create_menu_button(
            label,
            icon,
            key == DEFAULT_KEY
        )

        button.clicked.connect(
            lambda checked=False, k=key:
            self.page_requested.emit(k)
        )

        self.buttons[key] = button

        return button

    def set_active(self, key):

        for button_key, button in self.buttons.items():

            object_name = "activeButton" if button_key == key else ""
            if button.objectName() == object_name:
                continue
            button.setObjectName(object_name)

            button.style().unpolish(button)
            button.style().polish(button)

    # ======================================================
    # LOGO
    # ======================================================

    def _create_logo(self):

        container = QFrame()

        logo_layout = QHBoxLayout(container)

        logo_layout.setContentsMargins(
            8,
            0,
            0,
            12
        )

        logo_icon = QLabel()

        logo_icon.setFixedSize(38, 38)
        logo_icon.setAlignment(Qt.AlignCenter)

        logo_icon.setStyleSheet(theme.LOGO_ICON_QSS)

        logo_icon.setPixmap(
            qta.icon(
                "fa5s.cube",
                color="white"
            ).pixmap(20, 20)
        )

        name_container = QWidget()

        name_layout = QVBoxLayout(name_container)

        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(0)

        app_name = QLabel("Atlas")

        app_name.setStyleSheet(theme.APP_NAME_QSS)

        app_subtitle = QLabel("Stock Management")

        app_subtitle.setStyleSheet(theme.APP_SUBTITLE_QSS)

        name_layout.addWidget(app_name)
        name_layout.addWidget(app_subtitle)

        logo_layout.addWidget(logo_icon)
        logo_layout.addSpacing(8)
        logo_layout.addWidget(name_container)
        logo_layout.addStretch()

        return container

    # ======================================================
    # PEÇAS REPETIDAS
    # ======================================================

    def _create_divider(self):

        divider = QFrame()

        divider.setFixedHeight(1)

        divider.setStyleSheet(theme.DIVIDER_QSS)

        return divider

    def _create_section_title(self, text):

        label = QLabel(text)

        label.setStyleSheet(theme.SECTION_TITLE_QSS)

        return label

    # ======================================================
    # RODAPÉ DE USUÁRIO
    # ======================================================

    def _create_user_footer(self):

        container = QFrame()

        user_layout = QHBoxLayout(container)

        user_layout.setContentsMargins(
            4,
            0,
            4,
            0
        )

        avatar = QLabel("US")

        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(38, 38)

        avatar.setStyleSheet(theme.AVATAR_QSS)

        user_info = QWidget()

        user_info_layout = QVBoxLayout(user_info)

        user_info_layout.setContentsMargins(0, 0, 0, 0)
        user_info_layout.setSpacing(0)

        user_name = QLabel("Usuário")

        user_name.setStyleSheet(theme.USER_NAME_QSS)

        user_role = QLabel("Administrador")

        user_role.setStyleSheet(theme.USER_ROLE_QSS)

        user_info_layout.addWidget(user_name)
        user_info_layout.addWidget(user_role)

        self.logout_button = QPushButton()

        self.logout_button.setIcon(
            qta.icon(
                "fa5s.sign-out-alt",
                color="#9DB7E8"
            )
        )

        self.logout_button.setIconSize(QSize(16, 16))
        self.logout_button.setFixedSize(32, 32)

        self.logout_button.setStyleSheet(theme.LOGOUT_BUTTON_QSS)

        user_layout.addWidget(avatar)
        user_layout.addSpacing(8)
        user_layout.addWidget(user_info)
        user_layout.addStretch()
        user_layout.addWidget(self.logout_button)

        return container
