from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QStackedWidget,
)

from stockflow.application.services.product_service import ProductService
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.domain.permissions import (
    can_manage_products,
    can_manage_users,
    ensure_can_manage_users,
)
from stockflow.presentation.styles import theme
from stockflow.presentation.widgets.sidebar import Sidebar, DEFAULT_KEY
from stockflow.presentation.widgets.top_bar import TopBar
from stockflow.presentation.pages.coming_soon import ComingSoonPage
from stockflow.presentation.pages.estoque import EstoquePage
from stockflow.presentation.pages.novo_produto import NovoProdutoPage
from stockflow.presentation.pages.users import UsersPage
from stockflow.presentation.pages.vendas import VendasPage
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.presentation.pages.products import ProductsPage
from stockflow.presentation.pages.product_details import ProductDetailsPage


class MainWindow(QMainWindow):

    def __init__(self, session=None):
        super().__init__()

        # Sem sessão a janela abre SEM permissão de escrita. Assumir o ADMIN
        # da demonstração aqui concedia, em silêncio, exatamente o acesso que
        # esta tela existe para controlar: bastava construir `MainWindow()`
        # fora do login para receber o catálogo gravável. Quem precisa de
        # escrita informa a sessão (`MainWindow(conta_admin().session())`).
        self.session = session

        # Resultado da última tentativa de gravação. Serve para diagnóstico e
        # para os testes; NUNCA para decidir permissão — isso é do serviço.
        self.last_save_error = None

        # Resultado da última tentativa de navegação restrita. Mesmo
        # contrato do de gravação: diagnóstico e teste, NUNCA decisão de
        # permissão — isso é da política.
        self.last_navigation_error = None

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

        # O catálogo nasce antes das páginas: Estoque e Produtos recebem o
        # MESMO dict em que o repositório grava, e é essa identidade que faz
        # uma recarga mostrar o que acabou de ser salvo. Uma cópia por tela
        # compilaria igual e congelaria a lista na primeira montagem.
        self.products = dict(DEMO_PRODUCTS)
        # O serviço é quem aplica a regra de papel; o repositório só escreve
        # no catálogo em memória que as telas já compartilham.
        self.product_repository = DemoProductRepository(self.products)
        self.product_service = ProductService(self.product_repository)

        self.estoque_page = EstoquePage(self.products)

        self.novo_produto_page = NovoProdutoPage()

        self.editar_produto_page = NovoProdutoPage(edit_mode=True)

        self.products_page = ProductsPage(self.products)
        self.product_details_page = ProductDetailsPage()

        # Vendas e Usuários ficam como atributos: o botão de carrinho da
        # tabela de Usuários precisa alcançar o combo de clientes de Vendas.
        #
        # Vendas recebe o MESMO catálogo das demais telas; é essa identidade
        # que faz um produto desativado no Estoque deixar de ser oferecido
        # numa venda nova (US02). Uma cópia aqui ofereceria para sempre o
        # catálogo como ele estava quando a janela abriu.
        self.vendas_page = VendasPage(self.products)
        self.users_page = UsersPage()

        # A ordem de insercao reproduz os indices originais de main.py
        self.page_widgets = {
            "dashboard": dashboard_page,
            "estoque": self.estoque_page,
            "vendas": self.vendas_page,
            "produtos": self.products_page,
            "relatorios": ComingSoonPage("Relatórios"),
            "usuarios": self.users_page,
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

        self.users_page.user_table.venda_requested.connect(
            self._associar_cliente_e_abrir_vendas
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

        self.novo_produto_page.save_button.clicked.connect(self._save_new_product)
        self.editar_produto_page.save_button.clicked.connect(self._save_edited_product)

        for button in (self.novo_produto_page.back_button, self.novo_produto_page.cancel_button):
            button.clicked.connect(lambda: self.show_page(self._new_product_origin))

        for button in (self.editar_produto_page.back_button, self.editar_produto_page.cancel_button):
            button.clicked.connect(lambda: self.pages.setCurrentWidget(self.estoque_page))

        self.apply_session(self.session)

        self.show_page(DEFAULT_KEY)

    # Telas que exigem permissão para serem ABERTAS, não só para gravar.
    # Usuários entra aqui porque `fn_list_company_users` recusa o não-admin:
    # pelo banco, nem a listagem é dele.
    RESTRICTED_PAGES = {"usuarios": ensure_can_manage_users}

    def show_page(self, key):
        """Navega para uma página. Devolve `False` quando a recusa acontece.

        Esconder o item do menu é controle visual, e controle visual se
        burla: este método é chamável por sinal, por teste e por código
        futuro. A verificação mora aqui, no caminho que de fato troca a
        tela — o mesmo motivo pelo qual a gravação de produto é verificada
        no serviço e não no handler do botão.
        """
        guarda = self.RESTRICTED_PAGES.get(key)
        if guarda is not None:
            try:
                guarda(self.session, action="abrir a administração de usuários")
            except PermissionDeniedError as erro:
                # A janela não pode ficar meio-navegada: nem troca a página,
                # nem marca o item como ativo.
                self.last_navigation_error = erro
                QMessageBox.critical(self, "Acesso restrito", str(erro))
                return False

        self.last_navigation_error = None

        self.pages.setCurrentWidget(
            self.page_widgets[key]
        )

        self.sidebar.set_active(key)
        return True

    def _show_product_details(self, code):
        """Abre a ficha do produto escolhido no catálogo.

        Perdido no merge: _connect ligava product_requested a este método, que
        não existia mais. O acesso ao atributo levantava AttributeError ainda
        na construção da janela, e o login ficava parado sem explicação.
        """
        self.product_details_page.load_product(self.products.get(code))

        self.pages.setCurrentWidget(self.product_details_page)

    def _show_new_product(self, origin):
        """Abre o cadastro de produto lembrando de onde o usuário veio.

        O formulário é um widget único: abrir sem limpar entregaria ao
        próximo cadastro os campos da tentativa anterior. E o SKU é somente
        leitura na tela, então é aqui que ele precisa ser gerado — sem isso o
        campo manteria um código fixo e todo cadastro colidiria com o produto
        que já tem esse código.
        """
        self._new_product_origin = origin

        self.novo_produto_page.clear_form()
        self.novo_produto_page.set_catalog_options(
            self.product_repository.list_active_categories(),
            self.product_repository.list_active_units(),
        )
        self.novo_produto_page.set_code(self.product_repository.next_code())

        self.pages.setCurrentWidget(self.novo_produto_page)

    def _show_edit_product(self, product):
        """Abre a edição do produto escolhido na tabela de Estoque.

        O sinal da tabela traz a tupla de 6 campos montada na construção da
        página, a partir do catálogo de demonstração — e não de
        `self.products`. Editar por ela custava caro duas vezes: os campos
        ausentes na tupla (custo, unidade, ativo) eram gravados zerados, e a
        segunda edição do mesmo produto recarregava o estado ORIGINAL,
        desfazendo a primeira. Por isso aqui só o código é aproveitado: o
        produto que vai para o formulário vem sempre do catálogo vivo.
        """
        code = product[0] if isinstance(product, tuple) else product.code

        # Guardar qual produto está aberto deixa a edição independente do que
        # o widget mostra.
        self._editing_code = code

        self.editar_produto_page.set_catalog_options(
            self.product_repository.list_active_categories(),
            self.product_repository.list_active_units(),
        )
        self.editar_produto_page.load_product(self.products.get(code, product))

        self.pages.setCurrentWidget(
            self.editar_produto_page
        )
        
    # ======================================================
    # SESSÃO E PERMISSÃO
    # ======================================================

    def apply_session(self, session=None):
        """Aplica o papel da sessão a tudo que depende dele.

        Também é o caminho do relogin: a janela sobrevive ao logout, então
        reexibi-la sem reaplicar a sessão entregava ao novo usuário os
        controles liberados para o anterior.
        """
        if session is not None:
            self.session = session

        # `can_manage_products` já nega sessão ausente, então não há caminho
        # em que a janela sem login apareça com os controles liberados.
        pode_escrever = can_manage_products(self.session)

        self.novo_produto_page.apply_permission(pode_escrever)
        self.editar_produto_page.apply_permission(pode_escrever)
        self.estoque_page.new_product_button.setEnabled(pode_escrever)
        self.products_page.new_product_button.setEnabled(pode_escrever)
        self.estoque_page.stock_table.set_actions_enabled(pode_escrever)

        # Regra diferente da de produto: administrar usuário é só do ADMIN,
        # como `fn_is_admin`. Reaproveitar `pode_escrever` aqui entregaria a
        # tela de usuários ao estoquista.
        pode_gerenciar_usuarios = can_manage_users(self.session)

        self.users_page.apply_permission(pode_gerenciar_usuarios)
        self.sidebar.set_item_visible("usuarios", pode_gerenciar_usuarios)

        # Relogin: a janela sobrevive ao logout, então o ADMIN pode ter
        # deixado a tela de usuários na frente. Sem isto, o próximo usuário
        # entraria já olhando para ela.
        if not pode_gerenciar_usuarios and self.pages.currentWidget() is self.users_page:
            self.show_page(DEFAULT_KEY)

        self.sidebar.set_user(self.session)
        self.top_bar.set_user(self.session)

    # ======================================================
    # GRAVAÇÃO DE PRODUTO
    # ======================================================

    def _save_new_product(self):
        """Cadastra o produto do formulário.

        O handler não repete a checagem de papel de propósito: duas cópias da
        regra divergem com o tempo, e a que vale é a do serviço — a mesma que
        o `fn_has_role` do banco espelha.
        """
        data = self.novo_produto_page.collect_input()
        try:
            code = self.product_service.create_product(self.session, data)
        except PermissionDeniedError as erro:
            self._report_save_error("Cadastro não permitido", erro)
            return
        except ValueError as erro:
            self._report_save_error("Não foi possível cadastrar", erro)
            return

        self.last_save_error = None
        self._refresh_product_views(code)
        self.show_page(self._new_product_origin)

    def _save_edited_product(self):
        data = self.editar_produto_page.collect_input()
        code = getattr(self, "_editing_code", None) or data.code
        try:
            code = self.product_service.update_product(self.session, code, data)
        except PermissionDeniedError as erro:
            self._report_save_error("Edição não permitida", erro)
            return
        except LookupError as erro:
            self._report_save_error("Não foi possível salvar", erro)
            return
        except ValueError as erro:
            self._report_save_error("Não foi possível salvar", erro)
            return

        self.last_save_error = None
        self._refresh_product_views(code)
        self.pages.setCurrentWidget(self.estoque_page)

    def _report_save_error(self, titulo, erro):
        """Registra e mostra a recusa sem tocar no catálogo."""
        self.last_save_error = erro
        QMessageBox.critical(self, titulo, str(erro))

    def _refresh_product_views(self, code):
        """Reflete nas telas o produto recém-gravado.

        O repositório escreveu em `self.products`, mas NENHUMA tela relê esse
        dict sozinha — ler o dict compartilhado não é o mesmo que redesenhar:

        - Produtos: `ProductsPage` monta os cards uma única vez; sem o
          `reload_products` abaixo, o produto novo não ganhava card e o
          editado continuava mostrando os valores antigos.
        - Estoque: as linhas da tabela são itens criados na montagem, pelo
          mesmo motivo; `reload_products` as refaz a partir do catálogo. A
          permissão do papel é reaplicada dentro da `StockTable`, que recria
          os botões de ação — um botão novo nasce habilitado, e sem isso uma
          gravação devolveria editar/excluir a quem não pode gravar.
        - Ficha do produto: só é recarregada quando está aberta na frente.
        - Vendas: a oferta de produtos é um combo montado a partir dos
          ativos. Sem recarregar, o produto que acabou de ser desativado
          continuaria vendável até alguém reabrir a aplicação — e o recém
          cadastrado não apareceria. O histórico de vendas NÃO é tocado:
          suas linhas guardam o produto gravado na venda, não uma leitura
          do catálogo.
        """
        self.products_page.reload_products()
        self.estoque_page.reload_products()
        self.vendas_page.reload_products()

        produto = self.products.get(code)
        if produto is not None and self.pages.currentWidget() is self.product_details_page:
            self.product_details_page.load_product(produto)

    def _associar_cliente_e_abrir_vendas(self, nome_cliente):
        """Abre Vendas com o cliente já selecionado.

        Quando a associação falha, a página é aberta mesmo assim: o aviso
        preenchido por selecionar_cliente_externo explica o motivo e o foco
        vai para o combo, para seleção manual. Descartar o retorno fazia a
        navegação parecer bem-sucedida com o combo no placeholder.
        """
        associado = self.vendas_page.selecionar_cliente_externo(nome_cliente)

        self.show_page("vendas")

        if not associado:
            self.vendas_page.cliente_combo.setFocus()

        return associado
