from stockflow.presentation.styles import design_system as ds

from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
from stockflow.presentation.widgets.form_fields import _card, _card_header, _field, _line_edit, FIELD_QSS, FORM_CONTROL_QSS
from stockflow.presentation.styles import inventory
from stockflow.presentation.demo_data import base_de_clientes
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.application.services.sale_service import (
    DiscountApprovalRequired,
    FORMAS_DE_PAGAMENTO,
    SEM_ITENS,
    SaleService,
    parse_price,
    parse_quantity,
    parse_total,
)
from stockflow.infrastructure.repositories.demo_client_repository import DemoClientRepository
from stockflow.infrastructure.repositories.demo_movement_repository import (
    DemoMovementRepository,
)
from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
from stockflow.application.dto.sale_filter import (
    ORDENACOES,
    TAMANHO_PADRAO,
    SaleFilter,
)
from stockflow.domain.enums.sale_reversal_kind import SaleReversalKind
from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.domain.permissions import can_manage_clients
from stockflow.presentation.workers import executar_agora
from stockflow.domain.sale_discount import DiscountKind, calculate_discount



#: Cor do texto e do fundo do chip por situação, no molde de
#: `movimentacoes.py`. Cancelada e devolvida precisam ser distinguíveis
#: entre si, e não só de concluída: são operações diferentes.
CORES_DE_STATUS = {
    SaleStatus.CONCLUIDA.label: ("#166534", "#DCFCE7"),
    SaleStatus.CANCELADA.label: ("#8A3B3B", "#FBE9E9"),
    SaleStatus.DEVOLVIDA.label: ("#92400E", "#FEF3C7"),
    SaleStatus.PENDENTE.label: ("#334155", "#E2E8F0"),
}

PAGINACAO_BUTTON_QSS = """
QPushButton {
    background: #FFFFFF; color: #334155; border: 1px solid #CBD5F5;
    border-radius: 8px; padding: 0 14px; font-size: 13px;
}
QPushButton:hover:enabled { background: #EEF2FF; }
QPushButton:disabled { color: #94A3B8; border-color: #E2E8F0; }
"""


def _em_reais(valor):
    """Decimal -> "R$ 1.234,56", mesma grafia das linhas do histórico."""
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


class VendasPage(QWidget):
    """Checkout pelo catálogo, com quantidade, pagamento e desconto."""

    sale_registered = Signal(object)
    #: Identificador da venda cujo detalhe o usuário pediu.
    detalhes_requested = Signal(str)
    #: Identificador da venda recém-gravada cujo comprovante foi pedido
    #: (US19). "Emitir após a confirmação da venda" é a história literal, e
    #: a alternativa — mandar o operador caçar a venda no histórico — é
    #: exatamente o atrito que ela existe para remover.
    receipt_requested = Signal(str)

    def __init__(self, products=None, product_selection=None, parent=None, service=None, session=None, *, autoload=True):
        """Monta a tela sobre o catálogo compartilhado `code -> Product`.

        Sem argumento cai numa CÓPIA de `DEMO_PRODUCTS`, para a página
        continuar utilizável isolada sem escrever no catálogo do módulo. O
        caminho que importa é o outro: a `MainWindow` passa o MESMO dict que
        o Estoque grava, e é essa identidade que faz um produto desativado lá
        sumir da seleção de venda aqui.
        """
        super().__init__(parent)
        self.setObjectName("vendasPage")
        self.setStyleSheet(ds.page_qss("vendasPage") + FORM_CONTROL_QSS)

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
        self.execute = executar_agora
        self._saving = False
        self._loading = False
        self._pending_checkout = None
        self.service = service or SaleService(
            DemoSaleRepository(self.products), DemoClientRepository(), DemoProductRepository(self.products)
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
        if service is None:
            self.movement_repository = DemoMovementRepository(self.products)
            self.service = SaleService(
                DemoSaleRepository(self.products, self.movement_repository),
                DemoClientRepository(),
                DemoProductRepository(self.products),
            )
        else:
            self.service = service
            self.movement_repository = getattr(
                self.service.repository, "movements", None
            )
        self.client_repository = self.service.clients
        self.clientes = []
        self.historico_vendas = []
        # Estado da consulta do histórico (US17). `_pagina_atual` é base-um,
        # como o rótulo que o usuário lê; `_pagina` guarda o último
        # `SalePage` devolvido, de onde saem o total e o número de páginas.
        self._pagina_atual = 1
        self._pagina = None
        # O período só entra no filtro quando o usuário escolhe um: as duas
        # `QDateEdit` nascem preenchidas com hoje, e tratá-las como ativas
        # desde o início esconderia todo o histórico anterior a hoje.
        self.filtro_periodo_ativo = False
        # Carrinho da venda em montagem (US10). Vazio é o estado normal: a
        # venda de um produto só continua sendo feita direto no formulário,
        # sem obrigar a passar pelo carrinho para vender uma coisa.
        self.itens = []
        if autoload:
            self._carregar_dados()


        layout = QVBoxLayout(self)
        layout.setContentsMargins(ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN)
        layout.setSpacing(ds.SECTION_GAP)

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
        self.refresh_button.setFixedHeight(ds.CONTROL_HEIGHT)
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.reload_sales)
        heading.addWidget(self.refresh_button)
        layout.addLayout(heading)



        form_card = _card("saleForm")
        form_layout = form_card.layout()
        form_layout.addLayout(_card_header("fa5s.shopping-cart", "Nova venda", "Selecione o cliente e os produtos, confira o total e finalize a venda."))

        row = QHBoxLayout()
        row.setSpacing(12)

        # Combo para seleção de cliente
        self.cliente_combo = QComboBox()
        self.cliente_combo.setFixedHeight(ds.CONTROL_HEIGHT)
        self.cliente_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cliente_combo.setMinimumContentsLength(12)
        self.cliente_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.recarregar_clientes_disponiveis()
        self.cliente_combo.currentIndexChanged.connect(self._ao_selecionar_cliente)

        # Label de alerta para clientes inativos
        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #EF4444; font-size: 12px; font-weight: 500;")

        # Comprovante da venda que acabou de fechar (US19). Nasce escondido:
        # antes da primeira venda não há o que comprovar.
        self.receipt_button = QPushButton(" Emitir comprovante")
        self.receipt_button.setIcon(qta.icon("fa5s.file-invoice", color="#2563EB"))
        self.receipt_button.setAccessibleName("Emitir o comprovante da última venda")
        self.receipt_button.setCursor(Qt.PointingHandCursor)
        self.receipt_button.setFixedHeight(36)
        self.receipt_button.setStyleSheet(inventory.FILTER_QSS)
        self.receipt_button.setVisible(False)
        self.receipt_button.clicked.connect(self._pedir_comprovante)
        self._ultima_venda = None

        # Combo de produto: só entra aqui o que a política deixa vender.
        self.produto_combo = QComboBox()
        self.produto_combo.setFixedHeight(ds.CONTROL_HEIGHT)
        self.produto_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.produto_combo.setMinimumContentsLength(12)
        self.produto_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.recarregar_produtos_disponiveis()
        self.produto_combo.currentIndexChanged.connect(self._ao_selecionar_produto)

        self.qtd_input = QLineEdit()
        self.qtd_input.setPlaceholderText("Qtd")
        self.qtd_input.setFixedHeight(ds.CONTROL_HEIGHT)
        self.qtd_input.setMaximumWidth(100)
        self.qtd_input.setAccessibleName("Quantidade")

        self.val_input = QLineEdit()
        self.val_input.setPlaceholderText("R$ 0,00")
        self.val_input.setFixedHeight(ds.CONTROL_HEIGHT)
        self.val_input.setReadOnly(True)
        self.val_input.setAccessibleName("Preço unitário do catálogo")
        self.val_input.setMaximumWidth(170)
        self.val_input.setMinimumWidth(145)

        # Adicionar item é o que transforma a venda em multi-produto. Enquanto
        # ninguém clica aqui, a tela se comporta como sempre se comportou.
        self.add_button = btn_item = QPushButton(" Adicionar item")
        btn_item.setObjectName("primaryButton")
        btn_item.setStyleSheet(inventory.NEW_BUTTON_QSS)
        btn_item.setFixedHeight(ds.CONTROL_HEIGHT)
        btn_item.setIcon(qta.icon("fa5s.plus", color="white"))
        btn_item.clicked.connect(self._adicionar_item)

        self.save_button = btn_salvar = QPushButton("Finalizar venda")
        btn_salvar.setObjectName("primaryButton")
        btn_salvar.setStyleSheet(inventory.NEW_BUTTON_QSS)
        btn_salvar.setFixedHeight(ds.CONTROL_HEIGHT)
        btn_salvar.setIcon(qta.icon("fa5s.check", color="white"))
        btn_salvar.clicked.connect(self._registrar_venda)

        def campo(label, widget):
            group = QWidget()
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(4)
            title = QLabel(label)
            title.setBuddy(widget)
            group_layout.addWidget(title)
            group_layout.addWidget(widget)
            return group

        form_layout.addWidget(campo("Cliente", self.cliente_combo))
        row.addWidget(campo("Produto", self.produto_combo), 3)
        row.addWidget(campo("Quantidade", self.qtd_input), 1)
        row.addWidget(campo("Preço unitário", self.val_input), 1)
        form_layout.addLayout(row)
        item_actions = QHBoxLayout()
        self.stock_label = QLabel("Selecione um produto. Quantidade vazia equivale a 1.")
        self.stock_label.setWordWrap(True)
        item_actions.addWidget(self.stock_label, 1)
        item_actions.addWidget(btn_item)
        form_layout.addLayout(item_actions)

        # ------------------------------------------------------- carrinho
        #
        # Fica escondido enquanto está vazio: uma tabela vazia permanente
        # sugere que a venda exige montar carrinho, e ela não exige.
        self.itens_table = QTableWidget()
        self.itens_table.setColumnCount(7)
        self.itens_table.setHorizontalHeaderLabels([
            "Produto", "Qtd", "Preço unit.", "Subtotal bruto",
            "Tipo desc.", "Desconto", "Subtotal final",
        ])
        self.itens_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.itens_table.setStyleSheet(inventory.TABLE_QSS)
        self.itens_table.verticalHeader().setDefaultSectionSize(ds.ROW_HEIGHT)
        self.itens_table.setShowGrid(False)
        self.itens_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.itens_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.itens_table.verticalHeader().hide()
        self.itens_table.setFixedHeight(175)
        self.itens_table.setVisible(False)
        form_layout.addWidget(self.itens_table)

        fecho = QHBoxLayout()
        fecho.setSpacing(12)

        self.pagamento_combo = QComboBox()
        self.pagamento_combo.setFixedHeight(ds.CONTROL_HEIGHT)
        for forma in FORMAS_DE_PAGAMENTO:
            self.pagamento_combo.addItem(forma.capitalize(), forma)

        self.desconto_input = QLineEdit()
        self.desconto_input.setPlaceholderText("Desconto")
        self.desconto_input.setFixedHeight(ds.CONTROL_HEIGHT)
        self.desconto_tipo_combo = QComboBox()
        self.desconto_tipo_combo.addItem("R$", DiscountKind.FIXED.value)
        self.desconto_tipo_combo.addItem("%", DiscountKind.PERCENTAGE.value)
        self.desconto_tipo_combo.setFixedHeight(ds.CONTROL_HEIGHT)
        self.desconto_tipo_combo.setStyleSheet(
            FIELD_QSS.format(widget="QComboBox")
        )
        discount_editor = QWidget()
        discount_editor_layout = QHBoxLayout(discount_editor)
        discount_editor_layout.setContentsMargins(0, 0, 0, 0)
        discount_editor_layout.setSpacing(6)
        discount_editor_layout.addWidget(self.desconto_tipo_combo)
        discount_editor_layout.addWidget(self.desconto_input, 1)

        self.remove_button = btn_remover = QPushButton(" Remover último item")
        btn_remover.setFixedHeight(ds.CONTROL_HEIGHT)
        btn_remover.setStyleSheet(inventory.FILTER_QSS)
        btn_remover.clicked.connect(self._remover_ultimo_item)

        self.total_label = QLabel("")
        self.total_label.setStyleSheet(
            "color: #0F172A; font-size: 14px; font-weight: 600;"
        )

        fecho.addWidget(campo("Forma de pagamento", self.pagamento_combo), 1)
        fecho.addWidget(campo("Desconto total", discount_editor), 1)
        self.fecho_widget = QWidget()
        self.fecho_widget.setLayout(fecho)
        form_layout.addWidget(self.fecho_widget)
        checkout = QHBoxLayout()
        checkout.addWidget(self.total_label, 1)
        checkout.addWidget(btn_remover)
        checkout.addWidget(btn_salvar)
        btn_remover.setVisible(False)
        self.desconto_input.textChanged.connect(self._atualizar_total)
        self.desconto_tipo_combo.currentIndexChanged.connect(self._atualizar_total)
        self.qtd_input.textChanged.connect(self._atualizar_total)

        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QFrame.NoFrame)
        form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        form_scroll.setWidget(form_card)
        layout.addWidget(form_scroll, 3)
        # Total e ação principal permanecem visíveis mesmo em telas menores.
        layout.addLayout(checkout)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.receipt_button, 0, Qt.AlignLeft)

        table_card = _card("saleHistory")
        table_layout = table_card.layout()
        table_layout.addLayout(_card_header("fa5s.history", "Histórico de vendas", "Consulte os clientes e produtos registrados em cada venda."))
        # A busca livre continua, mas agora diz o que faz: ela filtra a
        # PÁGINA carregada, enquanto os campos abaixo consultam o banco.
        # Sem a distinção no rótulo, o usuário conclui que a busca não
        # encontra uma venda que está só na página seguinte.
        self.search_input = _line_edit("Buscar nesta página…")
        self.search_input.setAccessibleName("Buscar nesta página de vendas")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.addAction(qta.icon("fa5s.search", color="#94A3B8"), QLineEdit.LeadingPosition)
        self.search_input.textChanged.connect(self._filter_history)
        table_layout.addWidget(self.search_input)
        table_layout.addLayout(self._criar_filtros_do_historico())

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["ID Venda", "Cliente Associado", "Produto", "Valor Total", "Data",
             "Status", "Detalhes"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet(inventory.TABLE_QSS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(ds.ROW_HEIGHT)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
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
        self.retry_button = QPushButton("Atualizar histórico e clientes")
        self.retry_button.setFixedHeight(34)
        self.retry_button.setStyleSheet(inventory.FILTER_QSS)
        self.retry_button.clicked.connect(self.reload_sales)
        table_layout.addWidget(self.retry_button)
        table_layout.addWidget(self.table, 1)
        self.empty_label = QLabel("Nenhuma venda registrada.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(inventory.LIST_STATE_QSS)
        table_layout.addWidget(self.empty_label)
        self.result_count = QLabel()
        self.result_count.setStyleSheet("color: #64748B; font-size: 12px;")
        table_layout.addWidget(self.result_count)
        table_layout.addLayout(self._criar_controles_de_pagina())
        layout.addWidget(table_card, 1)

        self._recarregar_filtro_de_clientes()
        self.atualizar_tabela_historico()
        self._atualizar_paginacao()
        self._mostrar_estado_da_carga()
        self.apply_session(session)

    def _criar_filtros_do_historico(self):
        """Filtros que consultam o BANCO: ID, período, cliente, vendedor e
        situação, mais a ordenação (US17/SCRUM-219).

        Toda mudança aqui volta para a página 1 e dispara nova consulta.
        Ficar na página 5 de um filtro novo mostraria uma tela vazia que
        parece "não há vendas", quando o que houve foi deslocamento sem
        resultado.
        """
        linha = QHBoxLayout()
        linha.setSpacing(8)

        self.filtro_id = _line_edit("ID da venda")
        self.filtro_id.setAccessibleName("Filtrar por identificador da venda")
        self.filtro_id.setClearButtonEnabled(True)
        self.filtro_id.textChanged.connect(self._filtro_mudou)
        linha.addWidget(self.filtro_id, 2)

        hoje = QDate.currentDate()
        self.filtro_inicio = QDateEdit(hoje)
        self.filtro_inicio.setAccessibleName("Início do período")
        self.filtro_fim = QDateEdit(hoje)
        self.filtro_fim.setAccessibleName("Fim do período")
        for campo in (self.filtro_inicio, self.filtro_fim):
            campo.setCalendarPopup(True)
            campo.setDisplayFormat("dd/MM/yyyy")
            campo.setFixedHeight(38)
            # Mexer numa data LIGA o período: é a única leitura possível de
            # alguém escolhendo uma data, e exigir um botão "aplicar" só para
            # isso faria o campo parecer quebrado.
            campo.dateChanged.connect(self._periodo_mudou)
            linha.addWidget(campo, 1)

        self.filtro_cliente = QComboBox()
        self.filtro_cliente.setAccessibleName("Filtrar por cliente")
        self.filtro_cliente.setFixedHeight(38)
        self.filtro_cliente.currentIndexChanged.connect(self._filtro_mudou)
        linha.addWidget(self.filtro_cliente, 2)

        self.filtro_vendedor = QComboBox()
        self.filtro_vendedor.setAccessibleName("Filtrar por vendedor")
        self.filtro_vendedor.setFixedHeight(38)
        self.filtro_vendedor.currentIndexChanged.connect(self._filtro_mudou)
        linha.addWidget(self.filtro_vendedor, 2)

        self.filtro_status = QComboBox()
        self.filtro_status.setAccessibleName("Filtrar por situação")
        self.filtro_status.setFixedHeight(38)
        self.filtro_status.addItem("Todas as vendas finalizadas", None)
        for situacao in SaleStatus:
            self.filtro_status.addItem(situacao.label, situacao.value)
        self.filtro_status.currentIndexChanged.connect(self._filtro_mudou)
        linha.addWidget(self.filtro_status, 2)

        self.ordenacao_combo = QComboBox()
        self.ordenacao_combo.setAccessibleName("Ordenar vendas")
        self.ordenacao_combo.setFixedHeight(38)
        for codigo, rotulo in ORDENACOES:
            self.ordenacao_combo.addItem(rotulo, codigo)
        self.ordenacao_combo.currentIndexChanged.connect(self._filtro_mudou)
        linha.addWidget(self.ordenacao_combo, 2)

        self.limpar_filtros_button = QPushButton("Limpar filtros")
        self.limpar_filtros_button.setFixedHeight(38)
        self.limpar_filtros_button.setStyleSheet(inventory.FILTER_QSS)
        self.limpar_filtros_button.setCursor(Qt.PointingHandCursor)
        self.limpar_filtros_button.clicked.connect(self.limpar_filtros)
        linha.addWidget(self.limpar_filtros_button, 1)

        self._recarregar_filtro_de_clientes()
        return linha

    def _criar_controles_de_pagina(self):
        """Navegação de página: ‹ Anterior · página X de Y · Próximo ›."""
        linha = QHBoxLayout()
        linha.setSpacing(8)

        self.anterior_button = QPushButton("‹ Anterior")
        self.anterior_button.setAccessibleName("Página anterior de vendas")
        self.anterior_button.clicked.connect(
            lambda: self.ir_para_pagina(self._pagina_atual - 1)
        )
        self.paginacao_label = QLabel()
        self.paginacao_label.setAlignment(Qt.AlignCenter)
        self.paginacao_label.setStyleSheet("color: #64748B; font-size: 13px;")
        self.paginacao_label.setAccessibleName("Informação de paginação de vendas")
        self.proximo_button = QPushButton("Próximo ›")
        self.proximo_button.setAccessibleName("Próxima página de vendas")
        self.proximo_button.clicked.connect(
            lambda: self.ir_para_pagina(self._pagina_atual + 1)
        )
        for botao in (self.anterior_button, self.proximo_button):
            botao.setFixedHeight(32)
            botao.setStyleSheet(PAGINACAO_BUTTON_QSS)
        linha.addWidget(self.anterior_button)
        linha.addWidget(self.paginacao_label)
        linha.addWidget(self.proximo_button)
        linha.addStretch()
        return linha

    def _recarregar_filtro_de_clientes(self):
        """Clientes e vendedores presentes, com a escolha atual preservada.

        O filtro de cliente oferece TODOS os clientes conhecidos, inclusive
        inativos: o histórico de um cliente desativado continua existindo, e
        escondê-lo do filtro tiraria da tela a resposta para "o que esse
        cliente comprou". É o oposto do combo de venda nova, que só oferece
        ativos.
        """
        for combo, chave, rotulo, vazio in (
            (self.filtro_cliente, "client_id", "cliente", "Todos os clientes"),
            (self.filtro_vendedor, "seller_id", "seller", "Todos os vendedores"),
        ):
            escolhido = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(vazio, None)
            vistos = {}
            if chave == "client_id":
                for cliente in self.clientes:
                    vistos.setdefault(cliente["id"], cliente["nome"])
            for venda in self.historico_vendas:
                identificador = venda.get(chave)
                if identificador:
                    vistos.setdefault(identificador, venda.get(rotulo) or identificador)
            for identificador, nome in sorted(vistos.items(), key=lambda par: str(par[1]).casefold()):
                combo.addItem(str(nome), identificador)
            indice = combo.findData(escolhido) if escolhido else 0
            combo.setCurrentIndex(indice if indice >= 0 else 0)
            combo.blockSignals(False)

    def filtro_atual(self) -> SaleFilter:
        """Lê os widgets e monta o filtro. Fonte única do que está filtrado.

        A tela NÃO guarda uma cópia do filtro: guardar os dois leva a eles
        divergirem, e o sintoma é uma lista que não corresponde aos campos
        preenchidos.
        """
        return SaleFilter(
            sale_id=self.filtro_id.text().strip() or None,
            date_from=(self.filtro_inicio.date().toPython()
                       if self.filtro_periodo_ativo else None),
            date_to=(self.filtro_fim.date().toPython()
                     if self.filtro_periodo_ativo else None),
            client_id=self.filtro_cliente.currentData(),
            seller_id=self.filtro_vendedor.currentData(),
            status=self.filtro_status.currentData(),
            sort=self.ordenacao_combo.currentData() or "DATA_DESC",
        )

    def _periodo_mudou(self, *_):
        self.filtro_periodo_ativo = True
        self._filtro_mudou()

    def _filtro_mudou(self, *_):
        self.ir_para_pagina(1)

    def ir_para_pagina(self, numero):
        if self._loading or numero < 1:
            return
        self._pagina_atual = numero
        self.reload_sales()

    def limpar_filtros(self):
        """Zera TODOS os recortes de uma vez, numa consulta só.

        Os sinais ficam bloqueados durante a limpeza porque cada widget
        dispararia a sua própria consulta, e o usuário veria a lista piscar
        cinco vezes antes de assentar.
        """
        widgets = (self.filtro_id, self.filtro_cliente, self.filtro_vendedor,
                   self.filtro_status, self.ordenacao_combo,
                   self.filtro_inicio, self.filtro_fim)
        for widget in widgets:
            widget.blockSignals(True)
        self.filtro_id.clear()
        for combo in (self.filtro_cliente, self.filtro_vendedor,
                      self.filtro_status, self.ordenacao_combo):
            combo.setCurrentIndex(0)
        hoje = QDate.currentDate()
        self.filtro_inicio.setDate(hoje)
        self.filtro_fim.setDate(hoje)
        for widget in widgets:
            widget.blockSignals(False)
        self.filtro_periodo_ativo = False
        self.search_input.clear()
        self.ir_para_pagina(1)

    def _atualizar_paginacao(self):
        pagina = self._pagina
        total_paginas = pagina.pages if pagina else 1
        atual = pagina.page if pagina else 1
        self.paginacao_label.setText(f"Página {atual} de {total_paginas}")
        self.anterior_button.setEnabled(
            bool(pagina) and pagina.has_previous and not self._loading
        )
        self.proximo_button.setEnabled(
            bool(pagina) and pagina.has_next and not self._loading
        )

    def apply_session(self, session):
        self.session = session
        pode = can_manage_clients(session)
        self.save_button.setEnabled(pode and not self._saving and not self._loading)
        self.add_button.setEnabled(pode and not self._saving)

    def _carregar_dados(self):
        """Lê clientes e histórico, registrando a falha em vez de propagá-la.

        Devolve `True` quando as duas leituras passaram. Zera `last_error` no
        sucesso: falha transitória não pode deixar a tela marcada como
        quebrada para sempre.
        """
        # As duas leituras falham SEPARADAMENTE. Juntá-las num try só fazia
        # uma consulta de histórico quebrada esvaziar também o combo de
        # clientes — justamente o que a tela precisa para registrar a venda
        # que o usuário veio fazer.
        try:
            self.clientes = [
                {"id": c.client_id, "nome": c.name, "status": c.status}
                for c in self.service.clients.list_all()
            ]
        except Exception as erro:
            self.clientes = []
            self.last_error = erro

        try:
            # Filtro PADRÃO, e não `filtro_atual()`: este método roda no
            # construtor, antes de os widgets de filtro existirem.
            pagina = self.service.list_sales(
                self.session, SaleFilter(), 1, TAMANHO_PADRAO
            )
        except Exception as erro:
            self.last_error = erro
            # Lista vazia mantém a tela utilizável; o aviso é que diz ao
            # usuário que o vazio não é "não há vendas".
            self.historico_vendas = []
            self._pagina = None
            return False

        self._pagina = pagina
        self._pagina_atual = pagina.page
        self.historico_vendas = list(pagina.rows)
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
            self._filter_history()
            return
        self.load_error_label.setText(
            f"Não foi possível carregar o histórico de vendas.\n\n{self.last_error}"
        )
        self.load_error_label.setVisible(True)
        self.table.setVisible(False)
        self.empty_label.setVisible(False)

    def reload_sales(self):
        if self._saving or self._loading:
            return
        self._loading = True
        self.retry_button.setEnabled(False)
        self.retry_button.setText("Atualizando…")
        self.apply_session(self.session)

        def loaded(result):
            clientes, pagina = result
            self.clientes = [{"id": c.client_id, "nome": c.name, "status": c.status} for c in clientes]
            self._pagina = pagina
            self._pagina_atual = pagina.page
            self.historico_vendas = list(pagina.rows)
            self.last_error = None
            self.recarregar_clientes_disponiveis()
            self._recarregar_filtro_de_clientes()
            self.atualizar_tabela_historico()
            finish()

        def failed(error):
            self.last_error = error
            # A página velha não pode sobreviver a uma consulta que falhou:
            # ela mostraria resultado de um filtro que não é mais o da tela.
            self._pagina = None
            self.historico_vendas = []
            finish()

        def finish():
            self._loading = False
            self.retry_button.setEnabled(True)
            self.retry_button.setText("Atualizar histórico e clientes")
            self.apply_session(self.session)
            self._atualizar_paginacao()
            self._mostrar_estado_da_carga()

        session, filtro, numero = self.session, self.filtro_atual(), self._pagina_atual
        self.execute(
            lambda: (
                self.service.clients.list_all(),
                self.service.list_sales(session, filtro, numero, TAMANHO_PADRAO),
            ),
            loaded,
            failed,
        )

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

        # O carrinho ainda não foi vendido: sua prévia deve acompanhar o
        # catálogo que o serviço usará ao finalizar, inclusive após edição.
        for item in self.itens:
            product = self.products.get(item["codigo"])
            if product is not None:
                item.update(nome=product.name, preco=product.sale_price)
        self.recarregar_produtos_disponiveis()
        self._atualizar_carrinho()

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
        escolhido = self.produto_combo.currentData()
        produto = self.products.get(escolhido["codigo"]) if escolhido else None
        self.val_input.setText(produto.sale_price if produto else "")
        self.stock_label.setText(
            f"Disponível: {produto.stock} unidade(s)." if produto else
            "Selecione um produto. Quantidade vazia equivale a 1."
        )
        self._atualizar_total()


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

    def _produto_revalidado(self, escolhido):
        """Revalida contra o catálogo mesmo vindo de um combo só de ativos.

        O combo é uma foto do catálogo no momento da montagem, e a tela de
        Estoque pode desativar o produto com a tela de Vendas aberta — sem
        esta checagem a venda passaria assim mesmo.
        """
        try:
            return self.product_selection.ensure_selectable(
                escolhido["codigo"], OperationKind.VENDA
            )
        except (InactiveProductError, ProductNotFoundError) as erro:
            # Recarregar primeiro: a recarga mexe no combo e o sinal de
            # mudança limpa o aviso. Invertido, a mensagem sumiria na hora.
            self.recarregar_produtos_disponiveis()
            self.warning_label.setText(str(erro))
            return None

    def _adicionar_item(self):
        if self._saving:
            return False
        escolhido = self.produto_combo.currentData()
        if not escolhido:
            self.warning_label.setText("Selecione um produto ativo válido.")
            return False

        produto = self._produto_revalidado(escolhido)
        if produto is None:
            return False

        try:
            quantidade = parse_quantity(self.qtd_input.text().strip() or "1")
        except ValueError as erro:
            self.warning_label.setText(str(erro))
            return False

        # Mesmo produto duas vezes vira uma linha só: duas linhas do mesmo
        # item somam igual no total, mas a conferência na tela fica pior.
        for item in self.itens:
            if item["codigo"] == produto.code:
                try:
                    item["quantidade"] = parse_quantity(item["quantidade"] + quantidade)
                except ValueError as erro:
                    self.warning_label.setText(str(erro))
                    return False
                break
        else:
            self.itens.append({
                "codigo": produto.code,
                "nome": produto.name,
                "preco": produto.sale_price,
                "quantidade": quantidade,
                "discount_type": DiscountKind.FIXED.value,
                "discount_value": "0",
            })

        self.qtd_input.clear()
        self.produto_combo.setCurrentIndex(0)
        self.warning_label.setText("")
        self._atualizar_carrinho()
        return True

    def _remover_ultimo_item(self):
        if self._saving:
            return
        if self.itens:
            self.itens.pop()
            self._atualizar_carrinho()

    def _atualizar_carrinho(self):
        tem_itens = bool(self.itens)
        self.itens_table.setVisible(tem_itens)
        self.remove_button.setVisible(tem_itens)

        self.itens_table.setRowCount(len(self.itens))
        bruto = Decimal("0")
        for linha, item in enumerate(self.itens):
            preco = parse_price(item["preco"])
            subtotal = preco * item["quantidade"]
            bruto += subtotal
            self.itens_table.setItem(linha, 0, QTableWidgetItem(item["nome"]))
            self.itens_table.setItem(linha, 1, QTableWidgetItem(str(item["quantidade"])))
            self.itens_table.setItem(linha, 2, QTableWidgetItem(_em_reais(preco)))
            self.itens_table.setItem(linha, 3, QTableWidgetItem(_em_reais(subtotal)))
            kind = QComboBox()
            kind.addItem("R$", DiscountKind.FIXED.value)
            kind.addItem("%", DiscountKind.PERCENTAGE.value)
            kind.setCurrentIndex(max(0, kind.findData(item.get("discount_type", "FIXED"))))
            amount = QLineEdit(str(item.get("discount_value", "0")))
            amount.setPlaceholderText("0,00")
            amount.setFixedHeight(ds.CONTROL_HEIGHT)
            kind.currentIndexChanged.connect(
                lambda _index, row=item, combo=kind, editor=amount: self._item_discount_changed(
                    row, combo.currentData(), editor.text()
                )
            )
            amount.textChanged.connect(
                lambda value, row=item, combo=kind: self._item_discount_changed(
                    row, combo.currentData(), value
                )
            )
            self.itens_table.setCellWidget(linha, 4, kind)
            self.itens_table.setCellWidget(linha, 5, amount)
            self.itens_table.setItem(linha, 6, QTableWidgetItem(_em_reais(subtotal)))

        self._atualizar_total()

    def _item_discount_changed(self, item, discount_type, value):
        item["discount_type"] = discount_type
        item["discount_value"] = value
        self._atualizar_total()

    def _atualizar_total(self):
        bruto = sum((parse_price(i["preco"]) * i["quantidade"] for i in self.itens), Decimal("0"))
        desconto_itens = Decimal("0.00")
        for row, item in enumerate(self.itens):
            subtotal = parse_price(item["preco"]) * item["quantidade"]
            try:
                discount_value = parse_total(
                    item.get("discount_value", "0") or "0"
                )
            except ValueError:
                discount_value = Decimal("0.00")
            try:
                discount = calculate_discount(
                    subtotal,
                    item.get("discount_type", DiscountKind.FIXED.value),
                    discount_value,
                )
            except ValueError:
                self.total_label.setText("Confira os descontos dos itens.")
                return
            desconto_itens += discount
            final_cell = self.itens_table.item(row, 6)
            if final_cell is not None:
                final_cell.setText(_em_reais(subtotal - discount))
        escolhido = self.produto_combo.currentData()
        if escolhido:
            produto = self.products.get(escolhido["codigo"])
            try:
                if produto:
                    bruto += parse_price(produto.sale_price) * parse_quantity(self.qtd_input.text() or "1")
            except ValueError:
                self.total_label.setText("Confira a quantidade.")
                return
        if not self.itens and not escolhido:
            self.total_label.setText("")
            return

        try:
            valor_desconto = parse_total(self.desconto_input.text().strip() or "0")
        except ValueError:
            # Desconto meio digitado não pode apagar o total: o valor some da
            # tela justo enquanto o operador olha para ele.
            valor_desconto = Decimal("0.00")
        try:
            desconto = calculate_discount(
                bruto - desconto_itens,
                self.desconto_tipo_combo.currentData(),
                valor_desconto,
            )
        except ValueError:
            self.total_label.setText("Desconto maior que o total.")
            return
        total = bruto - desconto_itens - desconto
        self.total_label.setText(f"Total: {_em_reais(total)}")

    def _limpar_venda(self):
        self.itens = []
        self.val_input.clear()
        self.qtd_input.clear()
        self.desconto_input.clear()
        self.desconto_tipo_combo.setCurrentIndex(0)
        self.cliente_combo.setCurrentIndex(0)
        self.produto_combo.setCurrentIndex(0)
        self.warning_label.setText("")
        # A oferta é da venda que acabou de fechar; começar outra retira o
        # botão, para ninguém emitir o comprovante da venda anterior achando
        # que é o da que está montando.
        self._ultima_venda = None
        self.receipt_button.setVisible(False)
        self._atualizar_carrinho()

    def _venda_gravada(self, nova_venda):
        self._pending_checkout = None
        self.historico_vendas.insert(0, nova_venda)
        self._set_saving(False)
        self._limpar_venda()
        self.atualizar_tabela_historico()
        self.last_error = None
        self._mostrar_estado_da_carga()
        self._ultima_venda = str(nova_venda.get("id") or "")
        self.receipt_button.setVisible(bool(self._ultima_venda))
        self.sale_registered.emit(nova_venda)

    def _pedir_comprovante(self):
        if self._ultima_venda:
            self.receipt_requested.emit(self._ultima_venda)

    def _venda_recusada(self, erro):
        self._set_saving(False)
        if isinstance(erro, DiscountApprovalRequired):
            self._solicitar_autorizacao()
            return
        self.warning_label.setText(str(erro))

    def _set_saving(self, saving):
        self._saving = saving
        for widget in (self.cliente_combo, self.produto_combo, self.qtd_input,
                       self.pagamento_combo, self.desconto_tipo_combo,
                       self.desconto_input, self.itens_table, self.remove_button,
                       self.retry_button):
            widget.setEnabled(not saving)
        self.save_button.setText("Gravando…" if saving else " Finalizar Venda")
        self.apply_session(self.session)

    def _registrar_venda(self):
        if self._saving or self._loading:
            return
        data = self.cliente_combo.currentData()
        escolhido = self.produto_combo.currentData()

        # A ordem das recusas segue a ordem dos campos na tela: apontar o
        # último erro de um formulário meio vazio manda o usuário para o
        # campo errado.
        if not data:
            self.warning_label.setText("Selecione um cliente ativo válido.")
            return

        if escolhido and not self._adicionar_item():
            return
        if not self.itens:
            self.warning_label.setText(SEM_ITENS)
            return
        itens = [
            {
                "codigo": item["codigo"],
                "quantidade": item["quantidade"],
                "discount_type": item.get("discount_type", "FIXED"),
                "discount_value": item.get("discount_value", "0"),
            }
            for item in self.itens
        ]
        session, client_id = self.session, data["id"]
        payment = self.pagamento_combo.currentData()
        discount = self.desconto_input.text().strip() or "0"
        discount_type = self.desconto_tipo_combo.currentData()
        self._pending_checkout = (
            session, client_id, itens, payment, discount, discount_type
        )
        self._submit_checkout()

    def _submit_checkout(self, approval_credentials=None):
        if self._pending_checkout is None:
            return
        session, client_id, items, payment, discount, discount_type = (
            self._pending_checkout
        )
        self._set_saving(True)
        self.execute(
            lambda: self.service.register_sale(
                session, client_id, items, payment, discount, discount_type,
                approval_credentials,
            ),
            self._venda_gravada, self._venda_recusada,
        )

    def _solicitar_autorizacao(self):
        email, accepted = QInputDialog.getText(
            self,
            "Autorização de desconto",
            "E-mail do administrador:",
        )
        if not accepted:
            self.warning_label.setText(
                "Autorização cancelada. A venda não foi registrada."
            )
            return
        password, accepted = QInputDialog.getText(
            self,
            "Autorização de desconto",
            "Senha do administrador:",
            QLineEdit.Password,
        )
        if not accepted:
            self.warning_label.setText(
                "Autorização cancelada. A venda não foi registrada."
            )
            return
        self._submit_checkout((email, password))

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

            # Situação com chip colorido (US17/SCRUM-222). Sem esta coluna,
            # uma venda cancelada era desenhada idêntica a uma concluída, e o
            # histórico não respondia "esta venda ainda vale?".
            situacao = SaleStatus.from_value(venda.get("status") or "CONCLUIDA")
            celula = QTableWidgetItem(situacao.label)
            celula.setTextAlignment(Qt.AlignCenter)
            cor, fundo = CORES_DE_STATUS[situacao.label]
            celula.setForeground(QColor(cor))
            celula.setBackground(QColor(fundo))
            if situacao.revertida and venda.get("reversal_reason"):
                celula.setToolTip(
                    f"{SaleReversalKind.from_value(venda['reversal_kind']).label}: "
                    f"{venda['reversal_reason']}"
                )
            self.table.setItem(row, 5, celula)

            detail = "\n".join(
                f"{item['quantity']}x {item['product_name']}" for item in venda.get("items", [])
            )
            self.table.item(row, 2).setToolTip(detail or venda["produto"])
            self.table.setCellWidget(row, 6, self._botao_de_detalhes(venda["id"]))
        self._filter_history()

    def _botao_de_detalhes(self, sale_id):
        """Abre a venda. A listagem NÃO oferece cancelar nem devolver.

        Ação destrutiva mora no detalhe (US17/SCRUM-223): obrigar o
        administrador a abrir a venda antes de revertê-la é a distinção
        entre consultar e operar, e tira a ação de uma tabela densa onde ela
        estaria a um clique de distância.
        """
        botao = QPushButton()
        botao.setIcon(qta.icon("fa5s.eye", color="#1D4ED8"))
        botao.setToolTip("Ver detalhes da venda")
        botao.setAccessibleName(f"Ver detalhes da venda {sale_id}")
        botao.setCursor(Qt.PointingHandCursor)
        botao.setFlat(True)
        botao.clicked.connect(
            lambda _=False, i=sale_id: self.detalhes_requested.emit(str(i))
        )
        return botao

    def _filter_history(self):
        search = self.search_input.text().strip().casefold()
        visible = 0
        for row in range(self.table.rowCount()):
            matches = any(
                search in item.text().casefold() or search in item.toolTip().casefold()
                for column in range(self.table.columnCount())
                if (item := self.table.item(row, column)) is not None
            )
            self.table.setRowHidden(row, not matches)
            visible += matches
        total = self._pagina.total if self._pagina else self.table.rowCount()
        # Diz as DUAS grandezas: o que esta página mostra e quantas vendas o
        # filtro encontrou. Só a primeira faria o usuário concluir que o
        # histórico inteiro tem o tamanho da página.
        self.result_count.setText(
            f"{visible} nesta página · {total} venda(s) no filtro"
        )
        if self.filtro_atual().ativo or self.search_input.text().strip():
            vazio = "Nenhuma venda encontrada para estes filtros."
        else:
            vazio = "Nenhuma venda registrada nesta empresa."
        self.empty_label.setText(vazio)
        self.empty_label.setVisible(self.last_error is None and visible == 0)
