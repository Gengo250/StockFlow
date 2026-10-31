from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
)

from stockflow.application.services.movement_service import MovementService
from stockflow.application.services.product_service import ProductService
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.exceptions.adjustment_errors import SaldoDesatualizadoError
from stockflow.domain.permissions import (
    PERMISSION_MATRIX,
    TODOS_OS_PAPEIS,
    can_manage_companies,
    can_manage_suppliers,
    exigir_ver,
    pode_gravar,
    pode_ver,
)
from stockflow.presentation.backend import (
    build_catalog,
    build_client_repository,
    build_sale_repository,
    build_demo_user_directory,
    build_movement_repository,
    build_price_history_repository,
    build_supplier_repository,
    build_user_directory,
    set_user_active as set_directory_user_active,
    save_user,
    using_supabase,
)
from stockflow.presentation.workers import PageLoader, executar_agora, executar_em_segundo_plano
from stockflow.presentation.styles import theme
from stockflow.presentation.widgets.sidebar import (
    MENU_ITEMS,
    SYSTEM_ITEMS,
    Sidebar,
    DEFAULT_KEY,
)
from stockflow.presentation.widgets.top_bar import TopBar
from stockflow.presentation.widgets.page_stack import PageStack
from stockflow.presentation.pages.clientes import ClientesPage
from stockflow.presentation.pages.overview import DashboardPage, ReportsPage, SettingsPage, preference_prefix
from stockflow.presentation.pages.estoque import EstoquePage
from stockflow.presentation.pages.movimentacoes import MovimentacoesPage
from stockflow.presentation.pages.novo_produto import NovoProdutoPage
from stockflow.presentation.pages.historico_precos import HistoricoPrecosPage
from stockflow.presentation.pages.users import UsersPage
from stockflow.presentation.pages.vendas import VendasPage
from stockflow.presentation.pages.products import ProductsPage
from stockflow.presentation.pages.product_details import ProductDetailsPage
from stockflow.presentation.pages.sale_details import SaleDetailsPage
from stockflow.application.services.supplier_service import SupplierService
from stockflow.presentation.pages.suppliers import SuppliersPage


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

        # Diretório de usuários: buscado na primeira abertura da tela, não na
        # construção da janela. Ver `_carregar_usuarios_do_banco`.
        self._usuarios_carregados = False
        self.last_users_error = None
        self.last_user_status_error = None

        # Ver `_on_product_status_changed`: desfazer um toggle que falhou
        # reemite o sinal que o disparou.
        self._revertendo_situacao = False

        # Como o trabalho lento é executado. Atributo, e não import direto,
        # para que o teste possa substituir pela versão síncrona sem precisar
        # de um laço de eventos girando.
        self.executar_em_segundo_plano = executar_em_segundo_plano
        self._closed = False
        self._loaders = {}

        self.setWindowTitle("StockFlow")
        self.resize(1280, 800)

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
        if using_supabase() and self.pages.currentWidget() not in (self.estoque_page, self.products_page):
            self._reconsultar_estoque()

    # ======================================================
    # PÁGINAS
    # ======================================================

    def _create_pages(self):

        pages = PageStack()

        pages.setObjectName("pages")

        pages.setStyleSheet(theme.PAGES_QSS)


        # O catálogo nasce antes das páginas: Estoque e Produtos recebem o
        # MESMO dict em que o repositório grava, e é essa identidade que faz
        # uma recarga mostrar o que acabou de ser salvo. Uma cópia por tela
        # compilaria igual e congelaria a lista na primeira montagem.
        #
        # Quem decide entre demonstração e banco é `backend.build_catalog`,
        # por `STOCKFLOW_BACKEND`. A janela não sabe qual dos dois veio: a
        # porta é a mesma, e o serviço aplica a regra de papel por cima de
        # qualquer um deles.
        remote = using_supabase()
        self.products, self.product_repository = (
            build_catalog(self.session, load=False) if remote else build_catalog(self.session)
        )
        self.supplier_repository = build_supplier_repository(self.session)
        self.supplier_service = SupplierService(self.supplier_repository)
        self.product_service = ProductService(
            self.product_repository, self.supplier_repository
        )
        self.suppliers_page = SuppliersPage(self.supplier_service, self.session, autoload=not remote)

        self.estoque_page = EstoquePage(self.products)

        self.novo_produto_page = NovoProdutoPage()

        self.editar_produto_page = NovoProdutoPage(edit_mode=True)

        self.products_page = ProductsPage(self.products)
        self.product_details_page = ProductDetailsPage()
        self.sale_details_page = SaleDetailsPage()

        # Vendas e Usuários ficam como atributos: o botão de carrinho da
        # tabela de Usuários precisa alcançar o combo de clientes de Vendas.
        #
        # Vendas recebe o MESMO catálogo das demais telas; é essa identidade
        # que faz um produto desativado no Estoque deixar de ser oferecido
        # numa venda nova (US02). Uma cópia aqui ofereceria para sempre o
        # catálogo como ele estava quando a janela abriu.
        from stockflow.application.services.sale_service import SaleService
        self.client_repository = build_client_repository(self.session)
        self.sale_repository = build_sale_repository(self.session, self.products)
        self.movement_repository = build_movement_repository(
            self.session, self.products, self.supplier_repository
        )
        if not using_supabase():
            self.sale_repository.movements = self.movement_repository
        self.sale_service = SaleService(self.sale_repository, self.client_repository, self.product_repository)
        self.vendas_page = VendasPage(self.products, service=self.sale_service, session=self.session, autoload=not remote)
        self.clientes_page = ClientesPage(sales_page=self.vendas_page, repository=self.client_repository, session=self.session, autoload=not remote)
        self.users_page = UsersPage(users=() if using_supabase() else None, on_save=self._save_user)

        # Movimentações recebe o MESMO catálogo: a oferta de produtos tem que
        # acompanhar desativações feitas no Estoque, pela mesma razão da tela
        # de Vendas (US02).
        if using_supabase():
            self.vendas_page.execute = self._execute
        self.movement_service = MovementService(
            self.movement_repository, self.supplier_repository, self.product_repository
        )
        self.movimentacoes_page = MovimentacoesPage(self.products)

        # Histórico de preço e custo (H09). O serviço recebe a mesma sessão
        # das demais telas: a recusa de papel acontece nele, antes de gastar
        # a consulta que `fn_list_price_edits` recusaria de qualquer jeito.
        from stockflow.application.services.price_history_service import PriceHistoryService
        self.price_history_repository = build_price_history_repository(
            self.session, self.product_repository
        )
        self.price_history_service = PriceHistoryService(self.price_history_repository)
        self.historico_precos_page = HistoricoPrecosPage()
        # Consulta de rede no caminho de CONSTRUÇÃO: uma falha aqui subiria
        # até `__init__` e derrubaria a janela inteira, pelo mesmo motivo que
        # a carga de vendas derrubava. O combo de fornecedores vazio degrada
        # Movimentações; perder a janela tira o usuário do sistema todo.
        try:
            fornecedores = (
                self.supplier_service.list_suppliers(self.session)
                if not remote and can_manage_suppliers(self.session) else ()
            )
        except Exception as erro:
            self.supplier_load_error = erro
            fornecedores = ()
        else:
            self.supplier_load_error = None
        self.movimentacoes_page.set_suppliers(fornecedores)

        self.dashboard_page = DashboardPage(self.product_repository, self.sale_repository, self.client_repository)
        self.dashboard_page.navigate_requested.connect(self.show_page)
        self.reports_page = ReportsPage(
            self.product_repository,
            self.sale_repository,
            self.session,
            sale_service=self.sale_service,
            movement_service=self.movement_service,
            price_history_service=self.price_history_service,
        )
        self.settings_page = SettingsPage(self.session)
        self.settings_page.discount_limits_save_requested.connect(
            self._save_sale_discount_limit
        )
        if remote:
            if hasattr(type(self.product_repository), "list_snapshot"):
                self.dashboard_page.read_products = self.product_repository.list_snapshot
                self.reports_page.read_products = self.product_repository.list_snapshot
            for page in (self.dashboard_page, self.reports_page, self.clientes_page, self.suppliers_page):
                page.loader.execute = self._execute
        # A ordem de insercao reproduz os indices originais de main.py
        self.page_widgets = {
            "dashboard": self.dashboard_page,
            "estoque": self.estoque_page,
            "movimentacoes": self.movimentacoes_page,
            "fornecedores": self.suppliers_page,
            "clientes": self.clientes_page,
            "vendas": self.vendas_page,
            "produtos": self.products_page,
            "historico_precos": self.historico_precos_page,
            "relatorios": self.reports_page,
            "usuarios": self.users_page,
            "configuracoes": self.settings_page,
        }

        for page in self.page_widgets.values():
            pages.addWidget(page)

        pages.addWidget(self.novo_produto_page)

        pages.addWidget(self.editar_produto_page)
        pages.addWidget(self.product_details_page)
        pages.addWidget(self.sale_details_page)

        return pages

    # ======================================================
    # FIAÇÃO
    # ======================================================

    def _connect(self):

        self.sidebar.page_requested.connect(self.show_page)
        self.top_bar.search_input.returnPressed.connect(self._quick_search)
        self.top_bar.notifications_button.clicked.connect(self._show_notifications)
        self.novo_produto_page.draft_button.clicked.connect(self._save_product_draft)
        for pagina in (self.novo_produto_page, self.editar_produto_page):
            pagina.create_category = (
                lambda name, p=pagina: self.product_service.create_category(
                    self.session, name
                )
            )
        self.products_page.product_requested.connect(self._show_product_details)
        self.product_details_page.back_button.clicked.connect(
            lambda: self.show_page("produtos")
        )

        self.users_page.user_table.venda_requested.connect(
            self._associar_cliente_e_abrir_vendas
        )
        self.users_page.user_table.status_change_requested.connect(
            self._on_user_status_changed
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
        self.estoque_page.product_status_changed.connect(
            self._on_product_status_changed
        )

        self.movimentacoes_page.register_requested.connect(self._registrar_movimentacao)
        self.movimentacoes_page.confirm_requested.connect(self._confirmar_movimentacao)
        self.movimentacoes_page.cancel_requested.connect(self._cancelar_movimentacao)
        self.movimentacoes_page.adjust_requested.connect(self._aplicar_ajuste)
        self.historico_precos_page.filtro_alterado.connect(
            lambda _codigo: self._carregar_historico_precos()
        )
        self.suppliers_page.suppliers_changed.connect(self._refresh_supplier_options)
        self.vendas_page.sale_registered.connect(self._venda_registrada)
        self.vendas_page.detalhes_requested.connect(self._show_sale_details)
        self.sale_details_page.back_button.clicked.connect(
            lambda: self.show_page("vendas")
        )
        self.sale_details_page.cancel_requested.connect(self._cancelar_venda)
        self.sale_details_page.return_requested.connect(self._devolver_venda)

        self.novo_produto_page.save_button.clicked.connect(self._save_new_product)
        self.editar_produto_page.save_button.clicked.connect(self._save_edited_product)

        for button in (self.novo_produto_page.back_button, self.novo_produto_page.cancel_button):
            button.clicked.connect(lambda: self.show_page(self._new_product_origin))

        for button in (self.editar_produto_page.back_button, self.editar_produto_page.cancel_button):
            button.clicked.connect(lambda: self.pages.setCurrentWidget(self.estoque_page))

        self.apply_session(self.session)

        self.show_page(self.settings_page.start_page.currentData() or DEFAULT_KEY)

    # Telas que exigem permissão para serem ABERTAS, não só para gravar.
    # Usuários entra aqui porque `fn_list_company_users` recusa o não-admin:
    # pelo banco, nem a listagem é dele; Movimentações, porque o saldo decide
    # reposição e venda e `fn_register_movement` recusa o vendedor.
    #
    # Derivado da matriz, e não escrito à mão: área cujo `ver` não cobre os
    # três papéis entra aqui sozinha. A lista literal anterior precisava ser
    # lembrada a cada área nova — foi assim que `clientes` e `vendas` ficaram
    # de fora sem ninguém decidir isso.
    RESTRICTED_PAGES = frozenset(
        nome for nome, area in PERMISSION_MATRIX.items() if area.ver != TODOS_OS_PAPEIS
    )

    #: Nome da área como o usuário a vê no menu, para a mensagem de recusa.
    #: Antes, um ternário escolhia entre dois rótulos fixos e o vendedor
    #: barrado em Movimentações era informado de que não podia abrir a
    #: administração de usuários — uma tela que ele nem tinha pedido.
    AREA_LABELS = {chave: nome for chave, nome, _ in MENU_ITEMS + SYSTEM_ITEMS}

    def show_page(self, key):
        """Navega para uma página. Devolve `False` quando a recusa acontece.

        Esconder o item do menu é controle visual, e controle visual se
        burla: este método é chamável por sinal, por teste e por código
        futuro. A verificação mora aqui, no caminho que de fato troca a
        tela — o mesmo motivo pelo qual a gravação de produto é verificada
        no serviço e não no handler do botão.
        """
        if key in self.RESTRICTED_PAGES:
            try:
                exigir_ver(
                    self.session,
                    key,
                    action=f"abrir a tela de {self.AREA_LABELS.get(key, key)}",
                )
            except PermissionDeniedError as erro:
                # A janela não pode ficar meio-navegada: nem troca a página,
                # nem marca o item como ativo.
                self.last_navigation_error = erro
                QMessageBox.critical(self, "Acesso restrito", str(erro))
                return False

        self.last_navigation_error = None
        self.pages.setCurrentWidget(self.page_widgets[key])
        self.sidebar.set_active(key)

        if key == "dashboard":
            self.dashboard_page.refresh()
        if key == "relatorios":
            self.reports_page.refresh()
        if key in {"clientes", "vendas"}:
            try:
                if key == "clientes":
                    self.clientes_page.reload_table()
                else:
                    self.vendas_page.reload_sales()
            except Exception as error:
                QMessageBox.warning(self, "Não foi possível atualizar", str(error))
        if key == "usuarios":
            self._carregar_usuarios_do_banco()
        if key == "fornecedores":
            self.suppliers_page.session = self.session
            self.suppliers_page.reload_table()
        if key in {"estoque", "produtos"}:
            self._reconsultar_estoque()
        if key == "historico_precos":
            self._carregar_historico_precos()
        if key == "configuracoes" and can_manage_companies(self.session):
            self._load(
                "sale_discount_limits",
                lambda: self.sale_service.get_discount_limits(self.session),
                self.settings_page.set_discount_limits,
                self.settings_page.show_discount_limits_error,
            )
        if key == "movimentacoes":
            self._recarregar_movimentacoes()
            if using_supabase():
                self._load("movement_suppliers", lambda: self._active_suppliers(),
                           self.movimentacoes_page.set_suppliers,
                           self.movimentacoes_page.show_load_error)

        return True

    # ======================================================
    # MOVIMENTAÇÕES
    # ======================================================

    def _execute(self, fetch, loaded, failed):
        from shiboken6 import isValid

        def deliver(callback, value):
            if isValid(self) and not self._closed:
                callback(value)

        execute = self.executar_em_segundo_plano if using_supabase() else executar_agora
        return execute(fetch, lambda value: deliver(loaded, value),
                       lambda error: deliver(failed, error))

    def _save_sale_discount_limit(self, value):
        button = self.settings_page.save_discount_limits_button
        button.setEnabled(False)

        def saved(limits):
            self.settings_page.set_discount_limits(limits)
            self.settings_page.discount_limits_feedback.setText(
                "Limite do vendedor salvo."
            )
            button.setEnabled(True)

        def failed(error):
            self.settings_page.show_discount_limits_error(error)
            button.setEnabled(True)

        self._execute(
            lambda: self.sale_service.set_discount_limits(self.session, value),
            saved,
            failed,
        )

    def _load(self, key, fetch, loaded, failed):
        if key not in self._loaders:
            self._loaders[key] = PageLoader(self, self._execute)
        self._loaders[key].load(fetch, loaded, failed)

    def closeEvent(self, event):
        self._closed = True
        for loader in self.findChildren(PageLoader):
            loader.close()
        super().closeEvent(event)

    def _venda_registrada(self, venda):
        """Venda concluída invalida saldo, alertas e histórico de movimentos."""
        self._saldo_mudou()
        # Vendedores não têm acesso à listagem de movimentações.
        if pode_ver(self.session, "movimentacoes"):
            self._recarregar_movimentacoes()

    def _show_sale_details(self, sale_id):
        """Abre o detalhe da venda (US17/SCRUM-221).

        Carrega do SERVIÇO, não da linha da tabela: a linha é uma foto do
        momento da consulta, e o detalhe precisa do que está gravado agora —
        senão uma reversão feita noutra máquina não apareceria.
        """
        try:
            venda = self.sale_service.get_sale(self.session, sale_id)
        except PermissionDeniedError as erro:
            QMessageBox.critical(self, "Acesso restrito", str(erro))
            return
        except Exception as erro:
            QMessageBox.warning(self, "Não foi possível abrir a venda", str(erro))
            return
        if venda is None:
            QMessageBox.information(
                self,
                "Venda não encontrada",
                "Esta venda não está mais disponível para esta empresa.",
            )
            return
        self.sale_details_page.load_sale(venda, self.session)
        self.pages.setCurrentWidget(self.sale_details_page)

    def _cancelar_venda(self, sale_id, reason):
        self._reverter_venda(
            self.sale_service.cancel_sale, sale_id, reason, "cancelar"
        )

    def _devolver_venda(self, sale_id, reason):
        self._reverter_venda(
            self.sale_service.return_sale, sale_id, reason, "devolver"
        )

    def _reverter_venda(self, operacao, sale_id, reason, acao):
        """Reverter mexe no SALDO, então reconsulta o catálogo junto.

        Mesma razão de `_venda_registrada`: deixar o estoque desatualizado
        depois de uma reversão faria a próxima venda ser recusada por um
        saldo que a tela diz existir.
        """
        try:
            operacao(self.session, sale_id, reason)
        except PermissionDeniedError as erro:
            QMessageBox.critical(self, "Acesso restrito", str(erro))
            return
        except Exception as erro:
            QMessageBox.warning(
                self, f"Não foi possível {acao} a venda", str(erro)
            )
            return

        self.vendas_page.reload_sales()
        self._saldo_mudou()
        if pode_ver(self.session, "movimentacoes"):
            self._recarregar_movimentacoes()
        # Redesenha o detalhe com o vínculo recém-gravado, para o usuário ver
        # o resultado da operação na tela em que a pediu.
        try:
            venda = self.sale_service.get_sale(self.session, sale_id)
        except Exception:
            venda = None
        if venda is not None:
            self.sale_details_page.load_sale(venda, self.session)

    def _recarregar_movimentacoes(self):
        """Recarrega o histórico. A permissão já foi checada na navegação."""
        session = self.session
        self._load("movements", lambda: self.movement_service.list_movements(session),
                   self.movimentacoes_page.set_movements,
                   self.movimentacoes_page.show_load_error)

    def _registrar_movimentacao(self, dados):
        """Registra e, se foi pedido, já confirma.

        Confirmar muda o saldo, então a tela de Estoque precisa ser
        reconsultada — é literalmente o critério da US04 sobre não manter
        alerta desatualizado. Quando a movimentação nasce pendente, o saldo
        não mudou e reconsultar seria requisição à toa.
        """
        try:
            self.movement_service.register(self.session, dados)
        except PermissionDeniedError as erro:
            self.movimentacoes_page.mostrar_recusa(erro)
            return
        except ValueError as erro:
            self.movimentacoes_page.mostrar_recusa(erro)
            return
        except Exception as erro:
            self.last_save_error = erro
            QMessageBox.critical(self, "Não foi possível registrar", str(erro))
            return

        self.movimentacoes_page.limpar_formulario()
        self._recarregar_movimentacoes()
        if dados.confirm:
            self._saldo_mudou()

    def _carregar_historico_precos(self):
        """Recarrega a consulta de histórico e o seu filtro (H09).

        Papel sem alçada não é erro de tela: o item nem aparece no menu, mas
        a janela sobrevive ao logout, então aplicar a sessão de um estoquista
        sobre uma janela que estava no histórico passa por aqui. Esvaziar é a
        resposta honesta — mostrar a recusa num diálogo interromperia um
        relogin que deu certo.
        """
        page = self.historico_precos_page
        if not pode_ver(self.session, "historico_precos"):
            page.preencher_produtos(())
            page.carregar(())
            return

        page.preencher_produtos(
            sorted((p.code, p.name) for p in self.products.values())
        )
        session, code = self.session, page.produto_combo.currentData()

        def loaded(rows):
            self.last_history_error = None
            page.carregar(rows)

        def failed(error):
            self.last_history_error = error
            page.mostrar_recusa(error)

        self._load("history", lambda: self.price_history_service.list_changes(session, code),
                   loaded, failed)

    def _aplicar_ajuste(self, dados):
        """Ajuste manual: grava e reconsulta, porque o saldo mudou na hora.

        Ao contrário de `_registrar_movimentacao`, não há caso em que o saldo
        fique parado: ajuste nasce confirmado. Então `_saldo_mudou()` é
        incondicional.
        """
        try:
            self.movement_service.adjust(self.session, dados)
        except PermissionDeniedError as erro:
            self.movimentacoes_page.mostrar_recusa_de_ajuste(erro)
            return
        except SaldoDesatualizadoError as erro:
            # Recontagem, não falha: a mensagem já diz os dois saldos, e
            # recarregar o catálogo faz o campo "Saldo atual" mostrar o
            # número novo antes da próxima tentativa.
            self.movimentacoes_page.mostrar_recusa_de_ajuste(erro)
            self._saldo_mudou()
            return
        except ValueError as erro:
            self.movimentacoes_page.mostrar_recusa_de_ajuste(erro)
            return
        except Exception as erro:
            self.last_save_error = erro
            QMessageBox.critical(self, "Não foi possível ajustar", str(erro))
            return

        self.movimentacoes_page.limpar_ajuste()
        self._recarregar_movimentacoes()
        self._saldo_mudou()

    def _confirmar_movimentacao(self, movement_id):
        if not self._executar_movimentacao(
            self.movement_service.confirm, movement_id, "confirmar"
        ):
            return
        self._saldo_mudou()

    def _cancelar_movimentacao(self, movement_id):
        """Cancelar uma CONFIRMADA devolve o saldo, então também reconsulta."""
        if not self._executar_movimentacao(
            self.movement_service.cancel, movement_id, "cancelar"
        ):
            return
        self._saldo_mudou()

    def _executar_movimentacao(self, operacao, movement_id, nome) -> bool:
        try:
            operacao(self.session, movement_id)
        except PermissionDeniedError as erro:
            self.movimentacoes_page.mostrar_recusa(erro)
            return False
        except Exception as erro:
            self.last_save_error = erro
            QMessageBox.critical(self, f"Não foi possível {nome}", str(erro))
            return False

        self._recarregar_movimentacoes()
        return True

    def _saldo_mudou(self):
        """Uma operação confirmada alterou o saldo. Propaga para as telas.

        Dois caminhos, porque as duas fontes se comportam de forma diferente:

        - COM banco, o saldo foi recalculado pelo trigger e a foto local não
          sabe disso. Só reconsultando. Isso inclui vendas confirmadas.
        - SEM banco, a operação já escreveu no catálogo compartilhado; o que
          falta é redesenhar. Reconsultar sairia cedo (não há `load_catalog`)
          e a tela ficaria com o saldo antigo.
        """
        if getattr(self.product_repository, "load_catalog", None) is not None:
            self._reconsultar_estoque()
            return

        self.estoque_page.reload_products()
        self._publicar_alertas()
        self.products_page.reload_products()
        self.vendas_page.reload_products()
        self.movimentacoes_page.reload_products()

    def _reconsultar_estoque(self):
        """Reconsulta o catálogo ao ABRIR a tela de Estoque.

        A US04 pede que os alertas sejam reconsultados depois de uma
        movimentação confirmada mudar o saldo. As gravações feitas por ESTA
        janela já atualizam a foto na hora (write-through no repositório),
        mas uma movimentação confirmada por outra pessoa, ou por um caminho
        fora da UI, não teria como aparecer — e um alerta desatualizado é
        justamente o que o critério proíbe.

        Abrir a tela é o gatilho certo: é quando o usuário vai agir sobre a
        lista. Reconsultar a cada gravação custaria três requisições por
        salvamento e desfaria o write-through.

        No modo demonstração não há o que reconsultar: a foto É a fonte.
        """
        recarregar = getattr(self.product_repository, "load_catalog", None)
        if recarregar is None:
            # Sem banco não há catálogo a reconsultar, mas a consulta de
            # alerta existe nos DOIS adaptadores — e é dela que a tela tira
            # quem alerta. Pular isto deixaria a tela decidindo sozinha.
            self._publicar_alertas()
            return

        # FORA da thread da interface. A consulta são três requisições; feita
        # aqui, ela congelaria a janela entre `begin_loading` e o resultado —
        # e o aviso de "carregando" nunca chegaria a ser repintado, que foi
        # exatamente o motivo de ele existir e não aparecer.
        #
        # `executar` é atributo para o teste poder trocá-lo pela versão
        # síncrona: um teste de UI não tem laço de eventos girando, então uma
        # tarefa em segundo plano nunca entregaria resultado.
        # As DUAS consultas na mesma viagem. Separá-las faria a tela desenhar
        # o catálogo novo com o alerta velho por um instante, e cobraria uma
        # ida à rede a mais por abertura.
        self.estoque_page.begin_loading()
        self.products_page.load_status.setText("Carregando catálogo…")
        if "stock" not in self._loaders:
            self._loaders["stock"] = PageLoader(
                self, lambda *args: self.executar_em_segundo_plano(*args)
            )
        self._loaders["stock"].load(
            self._buscar_estoque,
            self._estoque_recarregado,
            self._stock_load_failed,
        )

    def _stock_load_failed(self, error):
        self.estoque_page.show_load_error(error)
        self.products_page.load_status.setText(
            f"Não foi possível carregar o catálogo. Abra a página novamente para tentar.\n{error}"
        )

    def _buscar_estoque(self):
        """Catálogo e alertas, com a falha do segundo ISOLADA do primeiro.

        As duas consultas vão juntas, mas não têm o mesmo peso: sem catálogo
        não há lista nenhuma, enquanto sem a consulta de alerta ainda há o
        cálculo local — o espelho declarado da mesma regra.

        Até aqui uma exceção em `list_alerts` subia pelo mesmo caminho do
        catálogo e derrubava a tela inteira. Foi o que aconteceu quando o
        código passou a pedir `product_code` da view antes de a migration que
        cria a coluna ter sido aplicada: o catálogo carregava normalmente e o
        usuário via uma tela de erro.
        """
        fetch = getattr(self.product_repository, "fetch_catalog", self.product_repository.load_catalog)
        catalogo = fetch()
        try:
            return catalogo, self.product_repository.list_alerts(), None
        except Exception as erro:
            return catalogo, None, erro

    def _estoque_recarregado(self, resultado):
        """Chegada das consultas, já de volta na thread da interface."""
        catalogo, alertas, erro_do_alerta = resultado
        if hasattr(self.product_repository, "apply_catalog"):
            catalogo = self.product_repository.apply_catalog(catalogo)
        self.estoque_page.reload_products(catalogo)

        if alertas is None:
            # A lista aparece; só a decisão de quem alerta volta a ser local.
            self.estoque_page.clear_alerts()
            self.last_load_error = erro_do_alerta
        else:
            self.estoque_page.set_alerts(alertas)

        self.products_page.reload_products(catalogo)
        self.vendas_page.reload_products(catalogo)
        self.movimentacoes_page.reload_products(catalogo)
        if pode_ver(self.session, "historico_precos"):
            self.historico_precos_page.preencher_produtos(
                sorted((p.code, p.name) for p in catalogo.values())
            )

    def _publicar_alertas(self):
        """Entrega à tela o resultado da consulta de alerta.

        Falha aqui não derruba a tela: sem o resultado, `EstoquePage` cai na
        situação já calculada na linha, que é o espelho declarado da mesma
        regra. Uma lista de alerta aproximada é melhor do que uma tela de
        estoque que não abre.
        """
        try:
            self.estoque_page.set_alerts(self.product_repository.list_alerts())
        except Exception as erro:
            # Volta ao cálculo local em vez de ficar com um resultado velho:
            # alerta desatualizado é pior do que alerta aproximado.
            self.estoque_page.clear_alerts()
            self.last_load_error = erro

    def _carregar_usuarios_do_banco(self):
        """Busca o diretório de usuários na PRIMEIRA abertura da tela.

        Sob demanda, e não na construção da janela, por dois motivos:

        1. `fn_list_company_users` recusa quem não é ADMIN. Buscar durante o
           `__init__` faria a janela de um SELLER morrer montando uma tela
           que ele nem pode abrir.
        2. É uma ida à rede que a maioria das sessões nunca precisa — quem
           entra para registrar venda não abre a administração de usuários.

        A navegação só chega aqui depois da guarda de permissão, então o
        papel já foi verificado. Uma recusa do BANCO neste ponto significa
        divergência entre a política da aplicação e a do banco, e por isso
        aparece como aviso em vez de passar batida.
        """
        if self._usuarios_carregados:
            return
        session = self.session
        previous_subtitle = self.users_page.subtitle.text()
        self.users_page.subtitle.setText("Carregando usuários…")

        def loaded(rows):
            if session is not self.session:
                return
            self.last_users_error = None
            if rows is not None:
                self.users_page.load_users(rows)
            else:
                self.users_page.subtitle.setText(previous_subtitle)
            self._usuarios_carregados = True

        def failed(error):
            self.last_users_error = error
            self.users_page.subtitle.setText(f"Não foi possível carregar usuários: {error}")
            QMessageBox.warning(self, "Não foi possível carregar os usuários",
                                f"{error}\n\nA tela segue mostrando os dados anteriores.")

        self._load("users", lambda: build_user_directory(session), loaded, failed)

    def _save_user(self, **data):
        save_user(self.session, **data)
        rows = build_user_directory(self.session) if using_supabase() else build_demo_user_directory()
        self.users_page.load_users(rows, from_database=using_supabase())

    def _on_user_status_changed(self, user_id, active):
        """Grava o status e repovoa a mesma tela com a origem atual."""
        try:
            set_directory_user_active(self.session, user_id, active)
            linhas = (
                build_user_directory(self.session)
                if using_supabase()
                else build_demo_user_directory()
            )
        except Exception as erro:
            self.last_user_status_error = erro
            QMessageBox.warning(
                self,
                "Não foi possível alterar o status",
                f"{erro}\n\nO status exibido não foi atualizado.",
            )
            if using_supabase():
                self._usuarios_carregados = False
            return

        self.last_user_status_error = None
        self.users_page.load_users(linhas, from_database=using_supabase())

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
        page = self.novo_produto_page
        self.pages.setCurrentWidget(page)
        page.save_button.setEnabled(False)

        def fetch():
            return (self.product_repository.list_active_categories(),
                    self.product_repository.list_active_units(),
                    self._active_suppliers(), self.product_repository.next_code())

        def loaded(result):
            categories, units, suppliers, code = result
            page.set_catalog_options(categories, units, suppliers)
            settings = self.settings_page.settings
            draft = settings.value(self.settings_page.prefix + "/product_draft", "")
            if draft:
                import json
                from types import SimpleNamespace
                try:
                    page.load_product(SimpleNamespace(**json.loads(draft)))
                except (ValueError, TypeError, AttributeError):
                    pass
            page.set_code(code)
            page.apply_permission(pode_gravar(self.session, "produtos"))

        self._load("new_product", fetch, loaded,
                   lambda error: self._report_save_error("Não foi possível carregar o cadastro", error))

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
        # Lista desde a US04 (o status é reescrito no lugar), tupla no
        # formato antigo de seis campos, ou o próprio `Product`. Checar só
        # `tuple` deixava a linha nova cair no ramo do objeto e morrer em
        # `AttributeError: 'list' object has no attribute 'code'`.
        code = product[0] if isinstance(product, (tuple, list)) else product.code

        # Guardar qual produto está aberto deixa a edição independente do que
        # o widget mostra.
        self._editing_code = code

        page = self.editar_produto_page
        product_atual = self.products.get(code, product)
        current_supplier_id = getattr(product_atual, "supplier_id", None)
        page.load_product(product_atual)
        self.pages.setCurrentWidget(page)
        page.save_button.setEnabled(False)

        def fetch():
            suppliers = list(self._active_suppliers())
            if current_supplier_id and all(s.supplier_id != current_supplier_id for s in suppliers):
                current = self.supplier_repository.get(current_supplier_id)
                if current is not None:
                    suppliers.append(current)
            return (self.product_repository.list_active_categories(),
                    self.product_repository.list_active_units(), suppliers)

        def loaded(options):
            page.set_catalog_options(*options)
            page.load_product(product_atual)
            page.apply_permission(pode_gravar(self.session, "produtos"))

        self._load("edit_product", fetch, loaded,
                   lambda error: self._report_save_error("Não foi possível carregar a edição", error))

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
            # Relogin: o diretório pertence ao usuário ANTERIOR. Sem invalidar,
            # o próximo ADMIN veria a lista da outra sessão — e, se as
            # empresas forem diferentes, usuários de outra empresa.
            if session is not self.session:
                self._usuarios_carregados = False
            self.session = session

        # `can_manage_products` já nega sessão ausente, então não há caminho
        # em que a janela sem login apareça com os controles liberados.
        self.clientes_page.apply_session(self.session, reload=not using_supabase())
        self.vendas_page.apply_session(self.session)
        self.settings_page.apply_session(self.session)
        # Escrita: cada área habilita os widgets que ela controla. As alçadas
        # continuam SEPARADAS de propósito — administrar usuário é só do
        # ADMIN, como `fn_is_admin`, e reaproveitar a permissão de produto
        # aqui entregaria a tela de usuários ao estoquista.
        pode_escrever = pode_gravar(self.session, "produtos")
        self.novo_produto_page.apply_permission(pode_escrever)
        self.editar_produto_page.apply_permission(pode_escrever)
        self.estoque_page.new_product_button.setEnabled(pode_escrever)
        self.products_page.new_product_button.setEnabled(pode_escrever)
        self.estoque_page.stock_table.set_actions_enabled(pode_escrever)
        self.users_page.apply_permission(pode_gravar(self.session, "usuarios"))
        self.movimentacoes_page.apply_permission(
            pode_gravar(self.session, "movimentacoes")
        )

        # Menu: um laço sobre a matriz, não uma chamada por área. Área nova
        # aparece ou some sozinha, conforme o `ver` que ela declarou.
        for chave in self.sidebar.buttons:
            self.sidebar.set_item_visible(chave, pode_ver(self.session, chave))

        # Relogin: a janela sobrevive ao logout, então o ADMIN pode ter
        # deixado uma tela restrita na frente. Sem isto, o próximo usuário
        # entraria já olhando para ela. Vale para toda área, e não só para as
        # três que alguém lembrou de listar.
        atual = self.pages.currentWidget()
        for chave, widget in self.page_widgets.items():
            if widget is atual and not pode_ver(self.session, chave):
                self.show_page(DEFAULT_KEY)
                break

        if not using_supabase():
            self._carregar_historico_precos()

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
        except Exception as erro:
            self._report_save_error("Não foi possível cadastrar", erro)
            return

        self.last_save_error = None
        self.settings_page.settings.remove(self.settings_page.prefix + "/product_draft")
        self._refresh_product_views(code)
        self.show_page(self._new_product_origin)

    def _active_suppliers(self):
        return tuple(
            supplier for supplier in self.supplier_service.list_suppliers(self.session)
            if supplier.active
        )

    def _refresh_supplier_options(self):
        """Atualiza seletores sem perder vínculos de registros históricos."""
        try:
            suppliers = self.supplier_service.list_suppliers(self.session)
        except Exception as error:
            self.last_save_error = error
            QMessageBox.warning(
                self, "Não foi possível atualizar fornecedores", str(error)
            )
            return
        active = tuple(s for s in suppliers if s.active)
        self.movimentacoes_page.set_suppliers(active)
        for page in (self.novo_produto_page, self.editar_produto_page):
            selected = page.supplier_input.currentData()
            options = list(active)
            current = next(
                (supplier for supplier in suppliers
                 if supplier.supplier_id == selected),
                None,
            )
            if current is not None and not current.active:
                options.append(current)
            page.set_catalog_options(
                self.product_repository.list_active_categories(),
                self.product_repository.list_active_units(),
                options,
            )
            if selected is not None:
                index = page.supplier_input.findData(selected)
                if index < 0:
                    page.supplier_input.addItem("Fornecedor inativo", selected)
                    index = page.supplier_input.findData(selected)
                page.supplier_input.setCurrentIndex(index)

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
        except Exception as erro:
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
        self.movimentacoes_page.reload_products()

        produto = self.products.get(code)
        if produto is not None and self.pages.currentWidget() is self.product_details_page:
            self.product_details_page.load_product(produto)

    def _on_product_status_changed(self, code):
        """PERSISTE o ativar/desativar e propaga para as outras telas.

        A gravação acontece aqui, e não na página: a tela de Estoque não
        conhece repositório nenhum — ela altera a própria linha e avisa. Sem
        esta chamada, desativar um produto mudava a tabela e não gravava
        nada; no modo demonstração funcionava por acidente, porque a página
        escreve no mesmo dict que o repositório usaria.

        Não chama `_refresh_product_views`: a tela de Estoque já se
        redesenhou sozinha dentro de `toggle_product_status`, e mandá-la
        recarregar de novo aqui refaria as linhas no meio do tratamento do
        clique que originou a mudança — trocando sob os pés do sinal a lista
        de onde o produto veio.
        """
        # Guarda de reentrância. O desfazer abaixo chama
        # `toggle_product_status`, que emite o MESMO sinal que nos trouxe
        # aqui: sem esta trava, uma falha de gravação entra em recursão
        # infinita entre desfazer e tentar de novo.
        if self._revertendo_situacao:
            return

        produto = self.products.get(code)
        if produto is not None:
            try:
                self.product_repository.set_active(code, bool(produto.active))
            except Exception as erro:
                # Desfaz na tela o que não entrou no banco. Deixar a linha
                # mostrando o estado novo seria pior do que a falha: o
                # usuário sairia convencido de que desativou.
                self.last_save_error = erro
                self._revertendo_situacao = True
                try:
                    self.estoque_page.toggle_product_status(
                        next(p for p in self.estoque_page.produtos if p[0] == code)
                    )
                finally:
                    self._revertendo_situacao = False
                QMessageBox.critical(
                    self, "Não foi possível alterar a situação", str(erro)
                )
                return

        # Ativar/desativar muda quem alerta: a consulta só considera ativos.
        self._publicar_alertas()
        self.products_page.reload_products()
        self.vendas_page.reload_products()
        self.movimentacoes_page.reload_products()

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
        # Navegar ANTES de escolher: entrar em "vendas" ressincroniza a lista
        # de clientes, e a recarga é justamente o que descartava a escolha —
        # e o aviso — feitos antes da troca de tela.
        self.show_page("vendas")

        associado = self.vendas_page.selecionar_cliente_externo(nome_cliente)

        if not associado:
            self.vendas_page.cliente_combo.setFocus()

        return associado

    def _cadastrar_categoria(self, page):
        """Cadastra uma categoria sem sair do formulário de produto.

        A empresa recém-criada não tem nenhuma, e o cadastro de produto
        exige categoria: sem esta porta, o primeiro produto era impossível
        de registrar pela tela.

        A categoria nova já fica selecionada — quem a cadastrou estava
        preenchendo um produto e ia escolhê-la em seguida de qualquer jeito.
        """
        from PySide6.QtWidgets import QInputDialog

        nome, confirmou = QInputDialog.getText(
            self, "Nova categoria", "Nome da categoria:"
        )
        if not confirmou:
            return None

        try:
            criada = self.product_service.create_category(self.session, nome)
        except PermissionDeniedError as erro:
            QMessageBox.critical(self, "Acesso restrito", str(erro))
            return None
        except Exception as erro:
            QMessageBox.warning(self, "Não foi possível cadastrar", str(erro))
            return None

        # Reconsultar em vez de acrescentar à lista da tela: se outra pessoa
        # cadastrou uma categoria nesta empresa, ela aparece aqui também.
        page.reload_categories(
            self.product_repository.list_active_categories(), selected=criada
        )
        return criada

    def _save_product_draft(self):
        import dataclasses
        import json
        from stockflow.domain.permissions import ensure_can_manage_products
        try:
            ensure_can_manage_products(self.session)
            payload = dataclasses.asdict(self.novo_produto_page.collect_input())
            self.settings_page.settings.setValue(self.settings_page.prefix + "/product_draft", json.dumps(payload))
            self.settings_page.settings.sync()
            QMessageBox.information(self, "Rascunho salvo", "Rascunho salvo neste dispositivo. Será restaurado no próximo cadastro desta conta.")
        except Exception as error:
            self._report_save_error("Não foi possível salvar o rascunho", error)

    def _quick_search(self):
        self.show_page("estoque")
        self.estoque_page.search_input.setText(self.top_bar.search_input.text())

    def _show_notifications(self):
        if not self.settings_page.notifications.isChecked():
            QMessageBox.information(self, "Alertas", "Os alertas estão desativados nas configurações deste dispositivo.")
            return
        try:
            rows = self.product_repository.list_alerts()
            lines = [f"{code}: saldo {stock}, mínimo {minimum}" for code, stock, minimum, _ in rows
                     if code in self.products and self.products[code].low_stock_alert]
            QMessageBox.information(self, "Alertas de estoque", "\n".join(lines) if lines else "Nenhum alerta de estoque no momento.")
        except Exception as error:
            QMessageBox.warning(self, "Não foi possível consultar alertas", str(error))
