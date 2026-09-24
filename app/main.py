import sys
import qtawesome as qta

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QStackedWidget,
)

from PySide6.QtCore import Qt, QSize

from pages.coming_soon import ComingSoonPage
from pages.estoque import EstoquePage
from pages.novo_produto import NovoProdutoPage


# ==========================================================
# FUNÇÃO PARA CRIAR BOTÕES DO MENU
# ==========================================================

def create_menu_button(text, icon_name, active=False):
    button = QPushButton(text)

    button.setIcon(
        qta.icon(
            icon_name,
            color="#BBD4FF"
        )
    )

    button.setIconSize(QSize(18, 18))
    button.setFixedHeight(42)

    if active:
        button.setObjectName("activeButton")

    return button


# ==========================================================
# APLICAÇÃO
# ==========================================================

app = QApplication(sys.argv)


# ==========================================================
# JANELA PRINCIPAL
# ==========================================================
window = QMainWindow()

window.setWindowTitle("Atlas")
window.resize(1920, 1080)

window.setWindowOpacity(1.0)

window.setStyleSheet("""
    QMainWindow {
        background-color: #F0F5FF;
    }
""")

# ==========================================================
# WIDGET CENTRAL
# ==========================================================

central_widget = QWidget()

central_widget.setObjectName("centralWidget")

central_widget.setStyleSheet("""
    QWidget#centralWidget {
        background-color: #F0F5FF;
    }
""")

main_layout = QHBoxLayout(central_widget)

main_layout.setContentsMargins(0, 0, 0, 0)
main_layout.setSpacing(0)


# ==========================================================
# SIDEBAR
# ==========================================================

sidebar = QFrame()

sidebar.setFixedWidth(240)

sidebar.setStyleSheet("""
    QFrame {
        background-color: #0E2971;
    }

    QLabel {
        background-color: transparent;
        color: white;
    }

    QPushButton {
        background-color: transparent;
        color: #D7E4FF;

        border: none;
        border-radius: 10px;

        text-align: left;

        padding: 10px 12px;

        font-size: 15px;
    }

    QPushButton:hover {
        background-color: #24479B;
    }

    QPushButton#activeButton {
        background-color: #4566B1;
        color: white;
        font-weight: 600;
    }
""")


# ==========================================================
# LAYOUT DA SIDEBAR
# ==========================================================

sidebar_layout = QVBoxLayout(sidebar)

sidebar_layout.setContentsMargins(
    12,
    18,
    12,
    16
)

sidebar_layout.setSpacing(6)


# ==========================================================
# LOGO + NOME
# ==========================================================

logo_container = QFrame()

logo_layout = QHBoxLayout(logo_container)

logo_layout.setContentsMargins(
    8,
    0,
    0,
    12
)


# Ícone
logo_icon = QLabel()

logo_icon.setFixedSize(38, 38)
logo_icon.setAlignment(Qt.AlignCenter)

logo_icon.setStyleSheet("""
    background-color: #365BB3;
    border-radius: 10px;
""")

logo_icon.setPixmap(
    qta.icon(
        "fa5s.cube",
        color="white"
    ).pixmap(20, 20)
)


# Nome + subtítulo
name_container = QWidget()

name_layout = QVBoxLayout(name_container)

name_layout.setContentsMargins(0, 0, 0, 0)
name_layout.setSpacing(0)

app_name = QLabel("Atlas")

app_name.setStyleSheet("""
    color: white;
    font-size: 15px;
    font-weight: 500;
""")

app_subtitle = QLabel("Stock Management")

app_subtitle.setStyleSheet("""
    color: #9DB7E8;
    font-size: 11px;
""")

name_layout.addWidget(app_name)
name_layout.addWidget(app_subtitle)

logo_layout.addWidget(logo_icon)
logo_layout.addSpacing(8)
logo_layout.addWidget(name_container)
logo_layout.addStretch()

sidebar_layout.addWidget(logo_container)


# ==========================================================
# DIVISÓRIA SUPERIOR
# ==========================================================

divider_top = QFrame()

divider_top.setFixedHeight(1)

divider_top.setStyleSheet("""
    background-color: #29458C;
""")

sidebar_layout.addWidget(divider_top)
sidebar_layout.addSpacing(10)


# ==========================================================
# MENU PRINCIPAL
# ==========================================================

menu_title = QLabel("MENU PRINCIPAL")

menu_title.setStyleSheet("""
    color: #5EAEF7;
    font-size: 12px;
    font-weight: 600;
    padding-left: 12px;
""")

sidebar_layout.addWidget(menu_title)
sidebar_layout.addSpacing(4)


# ==========================================================
# BOTÕES DO MENU
# ==========================================================

dashboard_button = create_menu_button(
    "Dashboard",
    "fa5s.home",
    True
)

estoque_button = create_menu_button(
    "Estoque",
    "fa5s.cube"
)

vendas_button = create_menu_button(
    "Vendas",
    "fa5s.chart-bar"
)

produtos_button = create_menu_button(
    "Produtos",
    "fa5s.box"
)

relatorios_button = create_menu_button(
    "Relatórios",
    "fa5s.file-alt"
)


sidebar_layout.addWidget(dashboard_button)
sidebar_layout.addWidget(estoque_button)
sidebar_layout.addWidget(vendas_button)
sidebar_layout.addWidget(produtos_button)
sidebar_layout.addWidget(relatorios_button)


# ==========================================================
# DIVISÓRIA SISTEMA
# ==========================================================

sidebar_layout.addSpacing(8)

divider_system = QFrame()

divider_system.setFixedHeight(1)

divider_system.setStyleSheet("""
    background-color: #29458C;
""")

sidebar_layout.addWidget(divider_system)
sidebar_layout.addSpacing(10)


# ==========================================================
# TÍTULO SISTEMA
# ==========================================================

system_title = QLabel("SISTEMA")

system_title.setStyleSheet("""
    color: #5EAEF7;
    font-size: 12px;
    font-weight: 600;
    padding-left: 12px;
""")

sidebar_layout.addWidget(system_title)
sidebar_layout.addSpacing(4)


# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

settings_button = create_menu_button(
    "Configurações",
    "fa5s.cog"
)

sidebar_layout.addWidget(settings_button)


# ==========================================================
# EMPURRA USUÁRIO PARA BAIXO
# ==========================================================

sidebar_layout.addStretch()


# ==========================================================
# DIVISÓRIA DO RODAPÉ
# ==========================================================

footer_divider = QFrame()

footer_divider.setFixedHeight(1)

footer_divider.setStyleSheet("""
    background-color: #29458C;
""")

sidebar_layout.addWidget(footer_divider)
sidebar_layout.addSpacing(10)


# ==========================================================
# USUÁRIO
# ==========================================================

user_container = QFrame()

user_layout = QHBoxLayout(user_container)

user_layout.setContentsMargins(
    4,
    0,
    4,
    0
)


# Avatar
avatar = QLabel("US")

avatar.setAlignment(Qt.AlignCenter)
avatar.setFixedSize(38, 38)

avatar.setStyleSheet("""
    background-color: #3482FF;
    color: white;

    border-radius: 10px;

    font-size: 14px;
""")


# Informações
user_info = QWidget()

user_info_layout = QVBoxLayout(user_info)

user_info_layout.setContentsMargins(0, 0, 0, 0)
user_info_layout.setSpacing(0)

user_name = QLabel("Usuário")

user_name.setStyleSheet("""
    color: white;
    font-size: 14px;
    font-weight: 600;
""")

user_role = QLabel("Administrador")

user_role.setStyleSheet("""
    color: #9DB7E8;
    font-size: 11px;
""")

user_info_layout.addWidget(user_name)
user_info_layout.addWidget(user_role)


# ==========================================================
# BOTÃO LOGOUT
# ==========================================================

logout_button = QPushButton()

logout_button.setIcon(
    qta.icon(
        "fa5s.sign-out-alt",
        color="#9DB7E8"
    )
)

logout_button.setIconSize(QSize(16, 16))
logout_button.setFixedSize(32, 32)

logout_button.setStyleSheet("""
    QPushButton {
        background-color: transparent;
        border: none;
    }

    QPushButton:hover {
        background-color: #24479B;
        border-radius: 8px;
    }
""")


user_layout.addWidget(avatar)
user_layout.addSpacing(8)
user_layout.addWidget(user_info)
user_layout.addStretch()
user_layout.addWidget(logout_button)

sidebar_layout.addWidget(user_container)


# ==========================================================
# PÁGINAS
# ==========================================================

pages = QStackedWidget()

pages.setObjectName("pages")

pages.setStyleSheet("""
    QStackedWidget#pages {
        background-color: #F0F5FF;
    }
""")


# ----------------------------------------------------------
# DASHBOARD
# ----------------------------------------------------------

dashboard_page = QWidget()

dashboard_page.setStyleSheet("""
    background-color: #F0F5FF;
""")


# ----------------------------------------------------------
# PÁGINAS "EM BREVE"
# ----------------------------------------------------------

estoque_page = EstoquePage()

novo_produto_page = NovoProdutoPage()

vendas_page = ComingSoonPage("Vendas")

produtos_page = ComingSoonPage("Produtos")

relatorios_page = ComingSoonPage("Relatórios")

configuracoes_page = ComingSoonPage("Configurações")


# ==========================================================
# ADICIONA AS PÁGINAS AO QSTACKEDWIDGET
# ==========================================================

pages.addWidget(dashboard_page)       # índice 0
pages.addWidget(estoque_page)         # índice 1
pages.addWidget(vendas_page)          # índice 2
pages.addWidget(produtos_page)        # índice 3
pages.addWidget(relatorios_page)      # índice 4
pages.addWidget(configuracoes_page)   # índice 5
pages.addWidget(novo_produto_page)

estoque_page.new_product_button.clicked.connect(
    lambda: pages.setCurrentWidget(
        novo_produto_page
    )
)

# botão voltar
novo_produto_page.back_button.clicked.connect(
    lambda: pages.setCurrentWidget(
        estoque_page
    )
)

# botão cancelar
novo_produto_page.cancel_button.clicked.connect(
    lambda: pages.setCurrentWidget(
        estoque_page
    )
)
# ==========================================================
# LISTA DOS BOTÕES
# ==========================================================

menu_buttons = [
    dashboard_button,
    estoque_button,
    vendas_button,
    produtos_button,
    relatorios_button,
    settings_button,
]


# ==========================================================
# FUNÇÃO PARA TROCAR DE PÁGINA
# ==========================================================

def change_page(index, selected_button):

    # Troca a página
    pages.setCurrentIndex(index)

    # Remove o estado ativo de todos
    for button in menu_buttons:
        button.setObjectName("")

        button.style().unpolish(button)
        button.style().polish(button)

    # Coloca o estado ativo no botão selecionado
    selected_button.setObjectName("activeButton")

    selected_button.style().unpolish(selected_button)
    selected_button.style().polish(selected_button)


# ==========================================================
# CONECTA OS BOTÕES
# ==========================================================

dashboard_button.clicked.connect(
    lambda: change_page(
        0,
        dashboard_button
    )
)

estoque_button.clicked.connect(
    lambda: change_page(
        1,
        estoque_button
    )
)

vendas_button.clicked.connect(
    lambda: change_page(
        2,
        vendas_button
    )
)

produtos_button.clicked.connect(
    lambda: change_page(
        3,
        produtos_button
    )
)

relatorios_button.clicked.connect(
    lambda: change_page(
        4,
        relatorios_button
    )
)

settings_button.clicked.connect(
    lambda: change_page(
        5,
        settings_button
    )
)


# ==========================================================
# LAYOUT PRINCIPAL
# ==========================================================

main_layout.addWidget(sidebar)
main_layout.addWidget(pages)

main_layout.setStretch(0, 0)
main_layout.setStretch(1, 1)


# ==========================================================
# FINALIZA JANELA
# ==========================================================

window.setCentralWidget(central_widget)

window.show()

sys.exit(app.exec())