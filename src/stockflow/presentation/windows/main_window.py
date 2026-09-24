from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QStackedWidget,
)

from stockflow.presentation.styles import theme
from stockflow.presentation.widgets.sidebar import Sidebar, DEFAULT_KEY
from stockflow.presentation.pages.coming_soon import ComingSoonPage
from stockflow.presentation.pages.estoque import EstoquePage
from stockflow.presentation.pages.novo_produto import NovoProdutoPage


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Atlas")
        self.resize(1920, 1080)

        self.setWindowOpacity(1.0)

        self.setStyleSheet(theme.MAIN_WINDOW_QSS)

        central_widget = QWidget()

        central_widget.setObjectName("centralWidget")

        central_widget.setStyleSheet(theme.CENTRAL_WIDGET_QSS)

        main_layout = QHBoxLayout(central_widget)

        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar()

        self.pages = self._create_pages()

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.pages)

        main_layout.setStretch(0, 0)
        main_layout.setStretch(1, 1)

        self._connect()

        self.setCentralWidget(central_widget)

    # ======================================================
    # PÁGINAS
    # ======================================================

    def _create_pages(self):

        pages = QStackedWidget()

        pages.setObjectName("pages")

        pages.setStyleSheet(theme.PAGES_QSS)

        dashboard_page = QWidget()

        dashboard_page.setStyleSheet(theme.DASHBOARD_PAGE_QSS)

        self.estoque_page = EstoquePage()

        self.novo_produto_page = NovoProdutoPage()

        # A ordem de insercao reproduz os indices originais de main.py
        self.page_widgets = {
            "dashboard": dashboard_page,
            "estoque": self.estoque_page,
            "vendas": ComingSoonPage("Vendas"),
            "produtos": ComingSoonPage("Produtos"),
            "relatorios": ComingSoonPage("Relatórios"),
            "configuracoes": ComingSoonPage("Configurações"),
        }

        for page in self.page_widgets.values():
            pages.addWidget(page)

        pages.addWidget(self.novo_produto_page)

        return pages

    # ======================================================
    # FIAÇÃO
    # ======================================================

    def _connect(self):

        self.sidebar.page_requested.connect(self.show_page)

        self.estoque_page.new_product_button.clicked.connect(
            lambda: self.pages.setCurrentWidget(
                self.novo_produto_page
            )
        )

        self.novo_produto_page.back_button.clicked.connect(
            lambda: self.pages.setCurrentWidget(
                self.estoque_page
            )
        )

        self.novo_produto_page.cancel_button.clicked.connect(
            lambda: self.pages.setCurrentWidget(
                self.estoque_page
            )
        )

        self.show_page(DEFAULT_KEY)

    def show_page(self, key):

        self.pages.setCurrentWidget(
            self.page_widgets[key]
        )

        self.sidebar.set_active(key)
