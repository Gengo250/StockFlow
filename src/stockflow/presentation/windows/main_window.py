from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QStackedWidget,
)

from stockflow.application.services.movement_service import MovementService
from stockflow.application.services.product_service import ProductService
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.permissions import (
    can_manage_products,
    can_manage_users,
    can_move_stock,
    ensure_can_manage_users,
    ensure_can_move_stock,
)
from stockflow.presentation.backend import (
    build_catalog,
    build_demo_user_directory,
    build_movement_repository,
    build_user_directory,
    set_user_active as set_directory_user_active,
    using_supabase,
)
from stockflow.presentation.workers import executar_em_segundo_plano
from stockflow.presentation.styles import theme
from stockflow.presentation.widgets.sidebar import Sidebar, DEFAULT_KEY
from stockflow.presentation.widgets.top_bar import TopBar
from stockflow.presentation.pages.clientes import ClientesPage
from stockflow.presentation.pages.coming_soon import ComingSoonPage
from stockflow.presentation.pages.estoque import EstoquePage
from stockflow.presentation.pages.movimentacoes import MovimentacoesPage
from stockflow.presentation.pages.novo_produto import NovoProdutoPage
from stockflow.presentation.pages.users import UsersPage
from stockflow.presentation.pages.vendas import VendasPage
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
        #
        # Quem decide entre demonstração e banco é `backend.build_catalog`,
        # por `STOCKFLOW_BACKEND`. A janela não sabe qual dos dois veio: a
        # porta é a mesma, e o serviço aplica a regra de papel por cima de
        # qualquer um deles.
        self.products, self.product_repository = build_catalog(self.session)
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
        self.clientes_page = ClientesPage(sales_page=self.vendas_page)
        self.users_page = UsersPage()

        # Movimentações recebe o MESMO catálogo: a oferta de produtos tem que
        # acompanhar desativações feitas no Estoque, pela mesma razão da tela
        # de Vendas (US02).
        self.movement_repository = build_movement_repository(
            self.session, self.products
        )
        self.movement_service = MovementService(self.movement_repository)
        self.movimentacoes_page = MovimentacoesPage(self.products)

        # A ordem de insercao reproduz os indices originais de main.py
        self.page_widgets = {
            "dashboard": dashboard_page,
            "estoque": self.estoque_page,
            "movimentacoes": self.movimentacoes_page,
            "clientes": self.clientes_page,
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
    RESTRICTED_PAGES = {
        "usuarios": ensure_can_manage_users,
        # Movimentar altera saldo, e saldo decide reposição e venda.
        # `fn_register_movement` recusa quem não é ADMIN/STOCK, então nem a
        # consulta do histórico é do vendedor.
        "movimentacoes": ensure_can_move_stock,
    }

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

        if key == "usuarios":
            self._carregar_usuarios_do_banco()
        if key == "estoque":
            self._reconsultar_estoque()
        if key == "movimentacoes":
            self._recarregar_movimentacoes()

        self.pages.setCurrentWidget(
            self.page_widgets[key]
        )

        self.sidebar.set_active(key)
        return True

    # ======================================================
    # MOVIMENTAÇÕES
    # ======================================================

    def _recarregar_movimentacoes(self):
        """Recarrega o histórico. A permissão já foi checada na navegação."""
        try:
            self.movimentacoes_page.set_movements(
                self.movement_service.list_movements(self.session)
            )
        except Exception as erro:
            self.movimentacoes_page.show_load_error(erro)

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
        """Uma movimentação confirmada alterou o saldo. Propaga para as telas.

        Dois caminhos, porque as duas fontes se comportam de forma diferente:

        - COM banco, o saldo foi recalculado pelo trigger e a foto local não
          sabe disso. Só reconsultando.
        - SEM banco, o repositório de movimentação já escreveu no catálogo
          compartilhado; o que falta é redesenhar. Reconsultar sairia cedo
          (não há `load_catalog`) e a tela ficaria com o saldo antigo — foi
          exatamente o que aconteceu: o catálogo marcava 13 e a tabela de
          Estoque seguia mostrando 18.
        """
        if getattr(self.product_repository, "load_catalog", None) is not None:
            self._reconsultar_estoque()
            return

        self.estoque_page.reload_products()
        self._publicar_alertas()
        self.products_page.reload_products()
        self.vendas_page.reload_products()

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
        self.executar_em_segundo_plano(
            self._buscar_estoque,
            self._estoque_recarregado,
            self.estoque_page.show_load_error,
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
        catalogo = self.product_repository.load_catalog()
        try:
            return catalogo, self.product_repository.list_alerts(), None
        except Exception as erro:
            return catalogo, None, erro

    def _estoque_recarregado(self, resultado):
        """Chegada das consultas, já de volta na thread da interface."""
        catalogo, alertas, erro_do_alerta = resultado
        self.estoque_page.reload_products(catalogo)

        if alertas is None:
            # A lista aparece; só a decisão de quem alerta volta a ser local.
            self.estoque_page.clear_alerts()
            self.last_load_error = erro_do_alerta
        else:
            self.estoque_page.set_alerts(alertas)

        self.products_page.reload_products(catalogo)
        self.vendas_page.reload_products(catalogo)

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
        try:
            linhas = build_user_directory(self.session)
        except Exception as erro:
            self.last_users_error = erro
            QMessageBox.warning(
                self,
                "Não foi possível carregar os usuários",
                f"{erro}\n\nA tela segue mostrando os dados anteriores.",
            )
            return

        self.last_users_error = None
        # `None` significa "sem banco configurado": a tela mantém a
        # demonstração com que nasceu. Lista vazia é resposta do banco e
        # precisa aparecer como vazia.
        if linhas is not None:
            self.users_page.load_users(linhas)
        self._usuarios_carregados = True

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
        # Lista desde a US04 (o status é reescrito no lugar), tupla no
        # formato antigo de seis campos, ou o próprio `Product`. Checar só
        # `tuple` deixava a linha nova cair no ramo do objeto e morrer em
        # `AttributeError: 'list' object has no attribute 'code'`.
        code = product[0] if isinstance(product, (tuple, list)) else product.code

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
            # Relogin: o diretório pertence ao usuário ANTERIOR. Sem invalidar,
            # o próximo ADMIN veria a lista da outra sessão — e, se as
            # empresas forem diferentes, usuários de outra empresa.
            if session is not self.session:
                self._usuarios_carregados = False
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

        pode_movimentar = can_move_stock(self.session)
        self.movimentacoes_page.apply_permission(pode_movimentar)
        self.sidebar.set_item_visible("movimentacoes", pode_movimentar)

        if not pode_movimentar and self.pages.currentWidget() is self.movimentacoes_page:
            self.show_page(DEFAULT_KEY)

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
