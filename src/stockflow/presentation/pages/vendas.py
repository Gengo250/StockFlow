from decimal import Decimal

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
from stockflow.presentation.styles import inventory
from stockflow.presentation.demo_data import base_de_clientes
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.application.services.sale_service import (
    FORMAS_DE_PAGAMENTO,
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
from stockflow.domain.permissions import can_manage_clients



def _em_reais(valor):
    """Decimal -> "R$ 1.234,56", mesma grafia das linhas do histórico."""
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


class VendasPage(QWidget):
    """Página provisória para simulação de vendas e associação de clientes."""

    sale_registered = Signal()

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
        self.setStyleSheet("""
            QWidget#vendasPage { background-color: #F0F5FF; }
            QLabel { background-color: transparent; }
            QFrame#card {
                background-color: #FFFFFF;
                border: 1px solid #DBEAFE;
                border-radius: 16px;
            }
            QLineEdit, QComboBox {
                background-color: white;
                color: #0F172A;
                border: 1px solid #BFDBFE;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QPushButton#primaryButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover { background-color: #1D4ED8; }
            QTableWidget { background-color: #FFFFFF; border: none; }
            QHeaderView::section {
                background-color: #F8FBFF;
                color: #64748B;
                border: none;
                border-bottom: 1px solid #DBEAFE;
                padding: 10px;
                font-size: 12px;
                font-weight: 600;
            }
        """)

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
                self.service.repository, "_movement_repository", None
            )
        self.client_repository = self.service.clients
        self.clientes = []
        self.historico_vendas = []
        # Carrinho da venda em montagem (US10). Vazio é o estado normal: a
        # venda de um produto só continua sendo feita direto no formulário,
        # sem obrigar a passar pelo carrinho para vender uma coisa.
        self.itens = []
        self._carregar_dados()


        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)

        # Cabeçalho
        title = QLabel("Registro e Seleção de Vendas")
        title.setStyleSheet("color: #0F172A; font-size: 26px; font-weight: 700;")
        layout.addWidget(title)

        # Card de Nova Venda
        form_card = QFrame()
        form_card.setObjectName("card")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(12)

        form_title = QLabel("Nova Venda")
        form_title.setStyleSheet("color: #1E3A8A; font-size: 16px; font-weight: 600;")
        form_layout.addWidget(form_title)

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

        self.qtd_input = QLineEdit()
        self.qtd_input.setPlaceholderText("Qtd")
        self.qtd_input.setFixedHeight(42)

        self.val_input = QLineEdit()
        self.val_input.setPlaceholderText("Valor (R$)")
        self.val_input.setFixedHeight(42)

        # Adicionar item é o que transforma a venda em multi-produto. Enquanto
        # ninguém clica aqui, a tela se comporta como sempre se comportou.
        self.add_button = btn_item = QPushButton(" Adicionar item")
        btn_item.setObjectName("primaryButton")
        btn_item.setFixedHeight(42)
        btn_item.setIcon(qta.icon("fa5s.plus", color="white"))
        btn_item.clicked.connect(self._adicionar_item)

        self.save_button = btn_salvar = QPushButton(" Finalizar Venda")
        btn_salvar.setObjectName("primaryButton")
        btn_salvar.setFixedHeight(42)
        btn_salvar.setIcon(qta.icon("fa5s.check", color="white"))
        btn_salvar.clicked.connect(self._registrar_venda)

        row.addWidget(self.cliente_combo, 2)
        row.addWidget(self.produto_combo, 2)
        row.addWidget(self.qtd_input, 1)
        row.addWidget(self.val_input, 1)
        row.addWidget(btn_item, 1)
        row.addWidget(btn_salvar, 1)
        form_layout.addLayout(row)

        # ------------------------------------------------------- carrinho
        #
        # Fica escondido enquanto está vazio: uma tabela vazia permanente
        # sugere que a venda exige montar carrinho, e ela não exige.
        self.itens_table = QTableWidget()
        self.itens_table.setColumnCount(4)
        self.itens_table.setHorizontalHeaderLabels(
            ["Produto", "Qtd", "Preço unit.", "Subtotal"]
        )
        self.itens_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.itens_table.setShowGrid(False)
        self.itens_table.verticalHeader().hide()
        self.itens_table.setFixedHeight(140)
        self.itens_table.setVisible(False)
        form_layout.addWidget(self.itens_table)

        fecho = QHBoxLayout()
        fecho.setSpacing(12)

        self.pagamento_combo = QComboBox()
        self.pagamento_combo.setFixedHeight(42)
        for forma in FORMAS_DE_PAGAMENTO:
            self.pagamento_combo.addItem(forma.capitalize(), forma)

        self.desconto_input = QLineEdit()
        self.desconto_input.setPlaceholderText("Desconto (R$)")
        self.desconto_input.setFixedHeight(42)

        self.remove_button = btn_remover = QPushButton(" Remover último item")
        btn_remover.setFixedHeight(42)
        btn_remover.clicked.connect(self._remover_ultimo_item)

        self.total_label = QLabel("")
        self.total_label.setStyleSheet(
            "color: #0F172A; font-size: 14px; font-weight: 600;"
        )

        fecho.addWidget(self.pagamento_combo, 1)
        fecho.addWidget(self.desconto_input, 1)
        fecho.addWidget(btn_remover, 1)
        fecho.addWidget(self.total_label, 2)
        self.fecho_widget = QWidget()
        self.fecho_widget.setLayout(fecho)
        self.fecho_widget.setVisible(False)
        form_layout.addWidget(self.fecho_widget)

        form_layout.addWidget(self.warning_label)

        layout.addWidget(form_card)

        # Tabela de Histórico de Vendas
        hist_title = QLabel("Histórico de Vendas Realizadas")
        hist_title.setStyleSheet("color: #0F172A; font-size: 18px; font-weight: 600;")
        layout.addWidget(hist_title)

        table_card = QFrame()
        table_card.setObjectName("card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["ID Venda", "Cliente Associado", "Produto", "Valor Total", "Data"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
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

        table_layout.addWidget(self.table)
        layout.addWidget(table_card, 1)

        self.atualizar_tabela_historico()
        self._mostrar_estado_da_carga()
        self.apply_session(session)

    def apply_session(self, session):
        self.session = session
        pode = can_manage_clients(session)
        self.save_button.setEnabled(pode)
        self.add_button.setEnabled(pode)

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

    def reload_sales(self):
        self._carregar_dados()
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
        escolhido = self.produto_combo.currentData()
        if not escolhido:
            self.warning_label.setText("Selecione um produto ativo válido.")
            return

        produto = self._produto_revalidado(escolhido)
        if produto is None:
            return

        try:
            quantidade = parse_quantity(self.qtd_input.text().strip() or "1")
        except ValueError as erro:
            self.warning_label.setText(str(erro))
            return

        # Mesmo produto duas vezes vira uma linha só: duas linhas do mesmo
        # item somam igual no total, mas a conferência na tela fica pior.
        for item in self.itens:
            if item["codigo"] == produto.code:
                item["quantidade"] += quantidade
                break
        else:
            self.itens.append({
                "codigo": produto.code,
                "nome": produto.name,
                "preco": produto.sale_price,
                "quantidade": quantidade,
            })

        self.qtd_input.clear()
        self.produto_combo.setCurrentIndex(0)
        self.warning_label.setText("")
        self._atualizar_carrinho()

    def _remover_ultimo_item(self):
        if self.itens:
            self.itens.pop()
            self._atualizar_carrinho()

    def _atualizar_carrinho(self):
        tem_itens = bool(self.itens)
        self.itens_table.setVisible(tem_itens)
        self.fecho_widget.setVisible(tem_itens)

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

        if not tem_itens:
            self.total_label.setText("")
            return

        try:
            desconto = parse_total(self.desconto_input.text().strip() or "0")
        except ValueError:
            # Desconto meio digitado não pode apagar o total: o valor some da
            # tela justo enquanto o operador olha para ele.
            desconto = Decimal("0")
        total = bruto - desconto if desconto <= bruto else bruto
        self.total_label.setText(f"Total: {_em_reais(total)}")

    def _limpar_venda(self):
        self.itens = []
        self.val_input.clear()
        self.qtd_input.clear()
        self.desconto_input.clear()
        self.cliente_combo.setCurrentIndex(0)
        self.produto_combo.setCurrentIndex(0)
        self.warning_label.setText("")
        self._atualizar_carrinho()

    def _registrar_venda_com_itens(self, client_id):
        try:
            nova_venda = self.service.register_sale(
                self.session,
                client_id,
                [{"codigo": i["codigo"], "quantidade": i["quantidade"]}
                 for i in self.itens],
                self.pagamento_combo.currentData(),
                self.desconto_input.text().strip() or "0",
            )
        except Exception as erro:
            self.warning_label.setText(str(erro))
            return
        self.historico_vendas.insert(0, nova_venda)
        self._limpar_venda()
        self.atualizar_tabela_historico()
        self.sale_registered.emit()

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

        # Carrinho montado manda: a venda é a soma dos itens, com forma de
        # pagamento e desconto, e o que estiver solto nos combos é ignorado.
        if self.itens:
            self._registrar_venda_com_itens(data["id"])
            return

        if not escolhido:
            self.warning_label.setText("Selecione um produto ativo válido.")
            return

        produto = self._produto_revalidado(escolhido)
        if produto is None:
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
        self._limpar_venda()
        self.sale_registered.emit()
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