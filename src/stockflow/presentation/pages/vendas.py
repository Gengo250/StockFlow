import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stockflow.application.services.product_selection_service import (
    ProductSelectionService,
)
from stockflow.domain.enums.operation_kind import OperationKind
from stockflow.domain.exceptions.inactive_product import InactiveProductError
from stockflow.domain.exceptions.product_not_found import ProductNotFoundError
from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.presentation.widgets.form_fields import _card, _card_header, _field, _line_edit, FIELD_QSS
from stockflow.presentation.styles import inventory
from stockflow.presentation.demo_data import base_de_clientes
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.application.services.sale_service import SaleService
from stockflow.infrastructure.repositories.demo_client_repository import DemoClientRepository
from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
from stockflow.domain.permissions import can_manage_clients



class VendasPage(QWidget):
    """Registro de vendas e consulta do histórico da empresa."""

    def __init__(self, products=None, product_selection=None, parent=None, service=None, session=None):
        """Monta a tela sobre o catálogo compartilhado `code -> Product`.

        Sem argumento cai numa CÓPIA de `DEMO_PRODUCTS`, para a página
        continuar utilizável isolada sem escrever no catálogo do módulo. O
        caminho que importa é o outro: a `MainWindow` passa o MESMO dict que
        o Estoque grava, e é essa identidade que faz um produto desativado lá
        sumir da seleção de venda aqui.
        """
        super().__init__(parent)
        self.setObjectName("vendasPage")
        self.setStyleSheet("QWidget#vendasPage { background: #F0F5FF; } QLabel { background: transparent; color: #334155; }")

        # Base de clientes para simulação [ID, Nome, Status].
        # Vem de demo_data, a mesma fonte da tabela de Usuários: enquanto as
        # duas telas mantinham listas próprias, usuário ativo lá podia não
        # existir aqui e a associação falhava sem explicação.
        self.clientes = base_de_clientes()

        # Catálogo e política de seleção (US02). O serviço é quem decide se
        # um produto pode entrar numa venda nova; a tela não olha `active`
        # por conta própria, para não virar uma segunda cópia da regra.
        self.products = dict(DEMO_PRODUCTS) if products is None else products
        self.product_selection = product_selection or ProductSelectionService(
            DemoProductRepository(self.products)
        )

        # Vendas históricas. Guardam o NOME do cliente e o código/nome do
        # produto como estavam no momento da venda — não uma referência ao
        # cadastro. Desativar ou remover o produto depois não pode esvaziar
        # a linha do que já aconteceu.
        #
        # VND-1001 aponta para PRD-004, que nem está mais no catálogo: é o
        # caso que prova que a consulta do histórico não depende do cadastro.
        self.session = session
        self.service = service or SaleService(
            DemoSaleRepository(), DemoClientRepository(), DemoProductRepository(self.products)
        )
        # A carga fica ISOLADA porque acontece dentro do construtor, e o
        # construtor roda durante `MainWindow._create_pages`. Sem o try, uma
        # consulta que falha aqui sobe até `MainWindow.__init__` e derruba a
        # JANELA INTEIRA: o usuário autentica e recebe "Não foi possível abrir
        # o StockFlow", sem Estoque, Produtos, Clientes nem Usuários — nenhum
        # dos quais depende de vendas. Foi exatamente o que um banco sem a
        # coluna `sales.client_name` provocou.
        #
        # Mesmo contrato de `SuppliersPage.reload_table`: guarda o erro, deixa
        # as listas vazias e segue construindo a tela.
        self.last_error = None
        self.clientes = []
        self.historico_vendas = []
        self._carregar_dados()


        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(18)

        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        title = QLabel("Vendas")
        title.setStyleSheet(inventory.TITLE_QSS)
        subtitle = QLabel("Registre vendas e acompanhe o histórico dos seus clientes.")
        subtitle.setStyleSheet(inventory.SUBTITLE_QSS)
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles, 1)
        self.refresh_button = QPushButton("Atualizar")
        self.refresh_button.setIcon(qta.icon("fa5s.sync-alt", color="#475569"))
        self.refresh_button.setStyleSheet(inventory.FILTER_QSS)
        self.refresh_button.setFixedHeight(42)
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.reload_sales)
        heading.addWidget(self.refresh_button)
        layout.addLayout(heading)

        form_card = _card("saleForm")
        form_layout = form_card.layout()
        form_layout.addLayout(_card_header("fa5s.shopping-cart", "Nova venda", "Selecione o cliente, o produto e informe o valor total."))

        row = QHBoxLayout()
        row.setSpacing(12)

        # Combo para seleção de cliente
        self.cliente_combo = QComboBox()
        self.cliente_combo.setFixedHeight(42)
        self.recarregar_clientes_disponiveis()
        self.cliente_combo.currentIndexChanged.connect(self._ao_selecionar_cliente)

        # Label de alerta para clientes inativos
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #EF4444; font-size: 12px; font-weight: 500;")

        # Combo de produto: só entra aqui o que a política deixa vender.
        self.produto_combo = QComboBox()
        self.produto_combo.setFixedHeight(42)
        self.recarregar_produtos_disponiveis()
        self.produto_combo.currentIndexChanged.connect(self._ao_selecionar_produto)

        self.val_input = QLineEdit()
        self.val_input.setPlaceholderText("Valor (R$)")
        self.val_input.setFixedHeight(42)

        self.save_button = btn_salvar = QPushButton("Finalizar venda")
        btn_salvar.setObjectName("primaryButton")
        btn_salvar.setFixedHeight(42)
        btn_salvar.setIcon(qta.icon("fa5s.check", color="white"))
        btn_salvar.clicked.connect(self._registrar_venda)

        for label, widget, stretch in (
            ("Cliente", self.cliente_combo, 2),
            ("Produto", self.produto_combo, 2),
            ("Valor total (R$)", self.val_input, 1),
        ):
            widget.setAccessibleName(label)
            widget.setStyleSheet(FIELD_QSS.format(widget=type(widget).__name__))
            if isinstance(widget, QComboBox):
                widget.setStyleSheet(widget.styleSheet() + "QComboBox::drop-down { border: none; width: 28px; }")
                widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                widget.setMinimumWidth(0)
            field = _field(label)
            field.layout().addWidget(widget)
            row.addWidget(field, stretch)
        btn_salvar.setStyleSheet(inventory.NEW_BUTTON_QSS + "QPushButton:disabled { background: #CBD5E1; color: #64748B; }")
        btn_salvar.setCursor(Qt.PointingHandCursor)
        form_layout.addLayout(row)
        actions = QHBoxLayout()
        self.warning_label.setWordWrap(True)
        actions.addWidget(self.warning_label, 1)
        actions.addWidget(btn_salvar)
        form_layout.addLayout(actions)

        layout.addWidget(form_card)

        table_card = _card("saleHistory")
        table_layout = table_card.layout()
        table_layout.addLayout(_card_header("fa5s.history", "Histórico de vendas", "Consulte os clientes e produtos registrados em cada venda."))
        self.search_input = _line_edit("Buscar venda, cliente ou produto…")
        self.search_input.setAccessibleName("Buscar vendas")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.addAction(qta.icon("fa5s.search", color="#94A3B8"), QLineEdit.LeadingPosition)
        self.search_input.textChanged.connect(self._filter_history)
        table_layout.addWidget(self.search_input)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["ID Venda", "Cliente Associado", "Produto", "Valor Total", "Data"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet(inventory.TABLE_QSS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()

        # Mesma estratégia de `MovimentacoesPage`: o aviso ocupa o lugar da
        # lista, e não um diálogo. Fechado o diálogo, o usuário ficaria diante
        # de uma tabela vazia e concluiria que não há vendas.
        self.load_error_label = QLabel()
        self.load_error_label.setWordWrap(True)
        self.load_error_label.setAccessibleName("Erro ao carregar vendas")
        self.load_error_label.setStyleSheet(inventory.LOAD_ERROR_QSS)
        self.load_error_label.setVisible(False)
        table_layout.addWidget(self.load_error_label)

        table_layout.addWidget(self.table, 1)
        self.empty_label = QLabel("Nenhuma venda registrada.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(inventory.LIST_STATE_QSS)
        table_layout.addWidget(self.empty_label)
        self.result_count = QLabel()
        self.result_count.setStyleSheet("color: #64748B; font-size: 12px;")
        table_layout.addWidget(self.result_count)
        layout.addWidget(table_card, 1)

        self.atualizar_tabela_historico()
        self._mostrar_estado_da_carga()
        self.apply_session(session)

    def apply_session(self, session):
        self.session = session
        self.save_button.setEnabled(can_manage_clients(session))

    def _carregar_dados(self):
        """Lê clientes e histórico, registrando a falha em vez de propagá-la.

        Devolve `True` quando as duas leituras passaram. Zera `last_error` no
        sucesso: falha transitória não pode deixar a tela marcada como
        quebrada para sempre.
        """
        try:
            self.clientes = [
                {"id": c.client_id, "nome": c.name, "status": c.status}
                for c in self.service.clients.list_all()
            ]
            self.historico_vendas = self.service.list_sales()
        except Exception as erro:
            self.last_error = erro
            # Listas vazias mantêm a tela utilizável; o aviso é que diz ao
            # usuário que o vazio não é "não há vendas".
            self.clientes = []
            self.historico_vendas = []
            return False
        self.last_error = None
        return True

    def _mostrar_estado_da_carga(self):
        """Falha fica NA ÁREA DA LISTA, como em Estoque e Movimentações.

        Diálogo some ao ser fechado e deixa uma tabela vazia indistinguível de
        "nenhuma venda registrada" — que é a leitura errada e a mais cara.
        """
        if self.last_error is None:
            self.load_error_label.setVisible(False)
            self.table.setVisible(True)
            return
        self.load_error_label.setText(
            f"Não foi possível carregar o histórico de vendas.\n\n{self.last_error}"
        )
        self.load_error_label.setVisible(True)
        self.table.setVisible(False)
        self.empty_label.hide()
        self.result_count.setText("Histórico indisponível")

    def reload_sales(self):
        self._carregar_dados()
        self.recarregar_clientes_disponiveis()
        self.atualizar_tabela_historico()
        self._mostrar_estado_da_carga()

    def recarregar_clientes_disponiveis(self):
        """Preenche o combo apenas com clientes ativos para novas associações.

        A escolha atual é reapontada depois da recarga, pelo mesmo motivo do
        combo de produtos: a lista é refeita toda vez que a tela de Clientes
        sincroniza — inclusive durante a navegação para cá — e perder a
        seleção no caminho fazia o cliente associado pela tela de Usuários
        chegar aqui com o combo no placeholder. Se o cliente escolhido tiver
        sido inativado, ele simplesmente não volta.
        """
        escolhido = self.cliente_combo.currentData()

        self.cliente_combo.clear()
        self.cliente_combo.addItem("Selecione um cliente...", None)

        for cli in self.clientes:
            # Clientes inativos não aparecem na seleção de nova venda
            if cli["status"] == "Ativo":
                self.cliente_combo.addItem(f"{cli['nome']} ({cli['id']})", cli)

        if escolhido:
            self._apontar_cliente(escolhido["id"])

    def _apontar_cliente(self, client_id):
        """Põe o combo no cliente pedido, se ele estiver na oferta."""
        for i in range(self.cliente_combo.count()):
            data = self.cliente_combo.itemData(i)
            if data and data.get("id") == client_id:
                self.cliente_combo.setCurrentIndex(i)
                return True
        return False

    def recarregar_produtos_disponiveis(self):
        """Preenche o combo apenas com produtos ativos para novas vendas.

        A escolha atual é reapontada depois da recarga: o combo é refeito
        toda vez que o catálogo muda, e perder a seleção no meio de uma
        venda obrigaria o usuário a procurar o produto de novo. Se o produto
        escolhido tiver sido desativado, ele simplesmente não volta.
        """
        escolhido = self.produto_combo.currentData()

        self.produto_combo.clear()
        self.produto_combo.addItem("Selecione um produto...", None)

        for produto in self.product_selection.available_products():
            self.produto_combo.addItem(
                f"{produto.name} ({produto.code})",
                {"codigo": produto.code, "nome": produto.name},
            )

        if escolhido:
            self._apontar_produto(escolhido["codigo"])

    def reload_products(self, products=None):
        """Refaz a oferta de produtos a partir do catálogo atual.

        O histórico NÃO é refeito aqui de propósito. Suas linhas guardam o
        produto gravado na venda; reconstruí-las a partir do catálogo é
        justamente o que apagaria a operação antiga cujo produto foi
        desativado ou removido.
        """
        if products is not None and products is not self.products:
            self.products = products
            self.product_selection = ProductSelectionService(
                DemoProductRepository(products)
            )

        self.recarregar_produtos_disponiveis()

    def _apontar_produto(self, codigo):
        """Põe o combo no produto pedido, se ele estiver na oferta."""
        for i in range(self.produto_combo.count()):
            data = self.produto_combo.itemData(i)
            if data and data.get("codigo") == codigo:
                self.produto_combo.setCurrentIndex(i)
                return True
        return False

    def selecionar_produto(self, codigo):
        """Escolhe o produto por código, recusando o que não pode ser vendido.

        Fora da oferta há três causas diferentes, e tratá-las como uma só
        esconde duas delas: o produto pode estar inativo (regra da US02), não
        existir (divergência entre quem pediu e o catálogo) ou estar ativo e
        ausente só porque o combo ficou velho. Quem distingue é a política.
        """
        if self._apontar_produto(codigo):
            self.warning_label.setText("")
            return True

        try:
            self.product_selection.ensure_selectable(codigo, OperationKind.VENDA)
        except (InactiveProductError, ProductNotFoundError) as erro:
            self.produto_combo.setCurrentIndex(0)
            self.warning_label.setText(str(erro))
            return False

        # Ativo e fora do combo: a oferta é que estava desatualizada.
        self.recarregar_produtos_disponiveis()
        if self._apontar_produto(codigo):
            self.warning_label.setText("")
            return True

        self.produto_combo.setCurrentIndex(0)
        self.warning_label.setText(
            f"O produto {codigo} não está disponível para venda."
        )
        return False

    def _ao_selecionar_produto(self, index):
        self.warning_label.setText("")

    def selecionar_cliente_externo(self, cliente_nome):
        """Permite que a tela de clientes peça para associar um cliente específico."""
        for i in range(self.cliente_combo.count()):
            data = self.cliente_combo.itemData(i)
            if data and data.get("nome") == cliente_nome:
                self.cliente_combo.setCurrentIndex(i)
                # setCurrentIndex não emite sinal quando o índice já era o
                # atual, então o aviso anterior precisa ser limpo aqui.
                self.warning_label.setText("")
                return True

        # Sair do combo tem duas causas distintas: o cliente existe mas não
        # está ativo, ou não existe na base. Relatar sempre "inativo" escondia
        # divergências entre a base de Vendas e a tabela de Usuários.
        cliente = next(
            (c for c in self.clientes if c["nome"] == cliente_nome), None
        )
        if cliente is None:
            self.warning_label.setText(
                f"O cliente '{cliente_nome}' não existe na base de vendas."
            )
        else:
            self.warning_label.setText(
                f"O cliente '{cliente_nome}' está {cliente['status'].lower()} "
                "e não pode ser selecionado."
            )
        return False

    def _ao_selecionar_cliente(self, index):
        self.warning_label.setText("")

    def _registrar_venda(self):
        data = self.cliente_combo.currentData()
        escolhido = self.produto_combo.currentData()
        valor = self.val_input.text().strip()

        # A ordem das recusas segue a ordem dos campos na tela: apontar o
        # último erro de um formulário meio vazio manda o usuário para o
        # campo errado.
        if not data:
            self.warning_label.setText("Selecione um cliente ativo válido.")
            return

        if not escolhido:
            self.warning_label.setText("Selecione um produto ativo válido.")
            return

        # Revalida contra o catálogo mesmo o produto tendo saído de um combo
        # que só lista ativos. O combo é uma foto do catálogo no momento da
        # montagem, e a tela de Estoque pode desativar o produto com a tela
        # de Vendas aberta — sem esta checagem a venda passaria assim mesmo.
        try:
            produto = self.product_selection.ensure_selectable(
                escolhido["codigo"], OperationKind.VENDA
            )
        except (InactiveProductError, ProductNotFoundError) as erro:
            # Recarregar primeiro: a recarga mexe no combo e o sinal de
            # mudança limpa o aviso. Invertido, a mensagem sumiria na hora.
            self.recarregar_produtos_disponiveis()
            self.warning_label.setText(str(erro))
            return

        if not valor:
            self.warning_label.setText("Informe o valor da venda.")
            return

        try:
            nova_venda = self.service.register(
                self.session, data["id"], produto.code, valor
            )
        except Exception as erro:
            self.warning_label.setText(str(erro))
            return
        self.historico_vendas.insert(0, nova_venda)
        self.val_input.clear()
        self.cliente_combo.setCurrentIndex(0)
        self.produto_combo.setCurrentIndex(0)
        self.warning_label.setText("")
        self.atualizar_tabela_historico()

    def atualizar_tabela_historico(self):
        self.table.setRowCount(len(self.historico_vendas))
        for row, venda in enumerate(self.historico_vendas):
            self.table.setItem(row, 0, QTableWidgetItem(venda["id"]))
            self.table.setItem(row, 1, QTableWidgetItem(venda["cliente"]))
            # O produto sai do que foi gravado na venda, NUNCA de uma
            # releitura do catálogo: é isso que mantém visível a operação
            # antiga cujo produto foi desativado ou saiu do cadastro.
            self.table.setItem(row, 2, QTableWidgetItem(venda["produto"]))
            self.table.setItem(row, 3, QTableWidgetItem(venda["valor"]))
            self.table.setItem(row, 4, QTableWidgetItem(venda["data"]))
            self.table.item(row, 3).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for column in range(5):
                item = self.table.item(row, column)
                item.setToolTip(item.text())
        self._filter_history()

    def _filter_history(self, *_):
        query = self.search_input.text().strip().casefold()
        visible = 0
        for row, sale in enumerate(self.historico_vendas):
            matches = query in " ".join(str(sale[key]) for key in ("id", "cliente", "produto")).casefold()
            self.table.setRowHidden(row, not matches)
            visible += matches
        self.empty_label.setText("Nenhuma venda corresponde à busca." if query else "Nenhuma venda registrada.")
        self.empty_label.setVisible(visible == 0 and self.last_error is None)
        self.result_count.setText(f"{visible} de {len(self.historico_vendas)} vendas" if self.last_error is None else "Histórico indisponível")
