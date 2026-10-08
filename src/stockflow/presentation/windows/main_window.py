from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QStackedWidget,
)

from stockflow.presentation.styles import theme
from stockflow.presentation.widgets.sidebar import Sidebar, DEFAULT_KEY
from stockflow.presentation.widgets.top_bar import TopBar
from stockflow.presentation.pages.coming_soon import ComingSoonPage
from stockflow.presentation.pages.estoque import EstoquePage
from stockflow.presentation.pages.movimentacoes import MovimentacoesPage
from stockflow.presentation.pages.novo_produto import NovoProdutoPage
from stockflow.presentation.pages.users import UsersPage
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.presentation.pages.products import ProductsPage
from stockflow.presentation.pages.product_details import ProductDetailsPage


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("StockFlow")
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

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.top_bar = TopBar()
        content_layout.addWidget(self.top_bar)
        content_layout.addWidget(self.pages, 1)

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(content)

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

        self.editar_produto_page = NovoProdutoPage(edit_mode=True)

        self.products = dict(DEMO_PRODUCTS)
        self.movimentacoes_page = MovimentacoesPage(self.products)
        self.products_page = ProductsPage(self.products)
        self.product_details_page = ProductDetailsPage()

        # A ordem de insercao reproduz os indices originais de main.py
        self.page_widgets = {
            "dashboard": dashboard_page,
            "estoque": self.estoque_page,
            "movimentacoes": self.movimentacoes_page,
            "vendas": ComingSoonPage("Vendas"),
            "produtos": self.products_page,
            "relatorios": ComingSoonPage("Relatórios"),
            "usuarios": UsersPage(),
            "configuracoes": ComingSoonPage("Configurações"),
        }

        for page in self.page_widgets.values():
            pages.addWidget(page)

        pages.addWidget(self.novo_produto_page)

        pages.addWidget(self.editar_produto_page)
        pages.addWidget(self.product_details_page)

        return pages

    # ======================================================
    # FIAÇÃO
    # ======================================================

    def _connect(self):

        self.sidebar.page_requested.connect(self.show_page)
        self.products_page.product_requested.connect(self._show_product_details)
        self.product_details_page.back_button.clicked.connect(
            lambda: self.show_page("produtos")
        )

        self._new_product_origin = "estoque"
        self.estoque_page.new_product_button.clicked.connect(
            lambda: self._show_new_product("estoque")
        )
        self.products_page.new_product_button.clicked.connect(
            lambda: self._show_new_product("produtos")
        )

        self.estoque_page.product_edit_requested.connect(
            self._show_edit_product
        )

        for button in (self.novo_produto_page.back_button, self.novo_produto_page.cancel_button):
            button.clicked.connect(lambda: self.show_page(self._new_product_origin))

        for button in (self.editar_produto_page.back_button, self.editar_produto_page.cancel_button):
            button.clicked.connect(lambda: self.pages.setCurrentWidget(self.estoque_page))

        self.show_page(DEFAULT_KEY)

    def show_page(self, key):

        self.pages.setCurrentWidget(
            self.page_widgets[key]
        )

        self.sidebar.set_active(key)

    def _show_edit_product(self, product):

        self.editar_produto_page.load_product(product)

        self.pages.setCurrentWidget(
            self.editar_produto_page
        )

    def _show_product_details(self, code):
        self.product_details_page.load_product(self.products.get(code))
        self.pages.setCurrentWidget(self.product_details_page)
        self.sidebar.set_active("produtos")

    def _show_new_product(self, origin):
        self._new_product_origin = origin
        self.pages.setCurrentWidget(self.novo_produto_page)
