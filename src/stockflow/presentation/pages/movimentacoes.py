"""Registrar, confirmar e cancelar movimentações de estoque.

A tela que faltava para fechar o ciclo: o saldo já era a soma das
movimentações confirmadas, mas as únicas movimentações que existiam eram as
que `fn_create_products` e `fn_update_products` geravam por tabela. Lançar
uma entrada ou uma saída avulsa só era possível por SQL.

DOIS PASSOS, NÃO UM. Registrar cria a intenção; confirmar é o que move o
saldo. A tela mantém os dois separados porque o banco os mantém — e porque é
a separação que permite alguém lançar o que vai acontecer e confirmar quando
aconteceu. Para o caso comum, lançar algo que já ocorreu, há o atalho
"Registrar e confirmar".
"""

import qtawesome as qta
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.movement_status import MovementStatus
from stockflow.domain.product_status import selectable_products
from stockflow.presentation.styles import inventory

COLUMNS = ("Produto", "Espécie", "Quantidade", "Situação", "Observação",
           "Quando", "Fornecedor", "Ações")
ACTIONS_COLUMN = len(COLUMNS) - 1

# Índices da tupla que o repositório devolve:
# (id, código, nome do produto, espécie, quantidade, situação, nota, quando)
MOV_ID, MOV_CODE, MOV_NAME, MOV_KIND, MOV_QTY, MOV_STATUS, MOV_NOTE, MOV_WHEN = range(8)

STATUS_COLORS = {
    MovementStatus.CONFIRMADA.label: ("#0F7B4F", "#E4F7EF"),
    MovementStatus.PENDENTE.label: ("#8A6A1F", "#FDF3DF"),
    MovementStatus.CANCELADA.label: ("#8A3B3B", "#FBE9E9"),
}


class MovimentacoesPage(QWidget):
    """Lançamento e histórico. Não conhece repositório nem banco.

    Emite o que o usuário pediu e espera que a janela faça acontecer — mesmo
    contrato das demais telas. É isso que permite construí-la isolada num
    teste, sem sessão e sem rede.
    """

    register_requested = Signal(object)     # MovementInput
    confirm_requested = Signal(str)         # id da movimentação
    cancel_requested = Signal(str)

    def __init__(self, products=None):
        super().__init__()
        self.setObjectName("movimentacoesPage")
        self.setStyleSheet(inventory.PAGE_QSS)

        # O MESMO dict da janela, nunca uma cópia. É essa identidade que faz
        # um produto desativado no Estoque sair da oferta aqui na hora — a
        # mesma razão pela qual Vendas e Estoque o compartilham. Copiar
        # congelaria a oferta no estado em que a janela abriu.
        self.products = {} if products is None else products
        self.movimentacoes = ()
        self._pode_movimentar = True
        self._suppliers = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)
        layout.addLayout(self._create_header())
        layout.addWidget(self._create_form())
        layout.addWidget(self._create_table(), 1)

        self.list_state_label = QLabel()
        self.list_state_label.setWordWrap(True)
        self.list_state_label.setStyleSheet(inventory.LIST_STATE_QSS)
        layout.addWidget(self.list_state_label)

        self.load_error_label = QLabel()
        self.load_error_label.setWordWrap(True)
        self.load_error_label.setAccessibleName("Erro ao carregar movimentações")
        self.load_error_label.setStyleSheet(inventory.LOAD_ERROR_QSS)
        self.load_error_label.setVisible(False)
        layout.addWidget(self.load_error_label)

        self.reload_products(self.products)
        self.set_movements(())

    # ======================================================
    # MONTAGEM
    # ======================================================

    def _create_header(self):
        layout = QHBoxLayout()
        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel("Movimentações de Estoque")
        titulo.setStyleSheet(inventory.TITLE_QSS)
        self.subtitle = QLabel("Entradas e saídas que compõem o saldo")
        self.subtitle.setStyleSheet(inventory.SUBTITLE_QSS)
        textos.addWidget(titulo)
        textos.addWidget(self.subtitle)
        container = QWidget()
        container.setLayout(textos)
        layout.addWidget(container)
        layout.addStretch()
        return layout

    def _create_form(self):
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(inventory.TABLE_CARD_QSS)
        fora = QVBoxLayout(card)
        fora.setContentsMargins(18, 16, 18, 16)
        fora.setSpacing(10)

        linha = QHBoxLayout()
        linha.setSpacing(10)

        self.produto_combo = QComboBox()
        self.produto_combo.setFixedHeight(42)
        self.produto_combo.setAccessibleName("Produto da movimentação")

        self.especie_combo = QComboBox()
        self.especie_combo.setFixedHeight(42)
        self.especie_combo.setAccessibleName("Espécie da movimentação")
        for especie in MovementKind:
            self.especie_combo.addItem(especie.label, especie)
        self.especie_combo.currentIndexChanged.connect(self._update_supplier_enabled)

        self.fornecedor_combo = QComboBox()
        self.fornecedor_combo.setFixedHeight(42)
        self.fornecedor_combo.setAccessibleName("Fornecedor da entrada")
        self.fornecedor_combo.addItem("Selecione um fornecedor...", None)

        self.quantidade_input = QSpinBox()
        self.quantidade_input.setRange(1, 999999)
        self.quantidade_input.setFixedHeight(42)
        self.quantidade_input.setAccessibleName("Quantidade")

        self.nota_input = QLineEdit()
        self.nota_input.setPlaceholderText("Observação (opcional)")
        self.nota_input.setFixedHeight(42)

        self.registrar_button = QPushButton(" Registrar")
        self.registrar_button.setFixedHeight(42)
        self.registrar_button.setIcon(qta.icon("fa5s.plus", color="#1D4ED8"))
        self.registrar_button.setIconSize(QSize(13, 13))
        self.registrar_button.clicked.connect(lambda: self._registrar(confirmar=False))

        self.registrar_confirmar_button = QPushButton(" Registrar e confirmar")
        self.registrar_confirmar_button.setFixedHeight(42)
        self.registrar_confirmar_button.setStyleSheet(inventory.NEW_BUTTON_QSS)
        self.registrar_confirmar_button.setIcon(qta.icon("fa5s.check", color="white"))
        self.registrar_confirmar_button.setIconSize(QSize(13, 13))
        self.registrar_confirmar_button.clicked.connect(
            lambda: self._registrar(confirmar=True)
        )

        linha.addWidget(self.produto_combo, 3)
        linha.addWidget(self.especie_combo, 1)
        linha.addWidget(self.fornecedor_combo, 2)
        linha.addWidget(self.quantidade_input, 1)
        linha.addWidget(self.nota_input, 3)
        linha.addWidget(self.registrar_button, 1)
        linha.addWidget(self.registrar_confirmar_button, 1)
        fora.addLayout(linha)

        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet(
            "color: #EF4444; font-size: 12px; font-weight: 500;"
        )
        fora.addWidget(self.warning_label)
        return card

    def _create_table(self):
        card = QFrame()
        card.setStyleSheet(inventory.TABLE_CARD_QSS)
        fora = QVBoxLayout(card)
        fora.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setStyleSheet(inventory.TABLE_QSS)
        cabecalho = self.table.horizontalHeader()
        cabecalho.setSectionResizeMode(QHeaderView.ResizeToContents)
        cabecalho.setSectionResizeMode(COLUMNS.index("Observação"), QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(56)
        fora.addWidget(self.table)
        return card

    # ======================================================
    # DADOS
    # ======================================================

    def reload_products(self, products=None):
        """Oferece apenas produtos ATIVOS, como as demais telas de operação.

        Movimentar um produto desativado é a mesma contradição que vendê-lo:
        ele está fora de operação. A política é a mesma da US02, e vem do
        mesmo lugar, para que não haja duas noções de "produto disponível".
        """
        if products is not None:
            self.products = products

        atual = self.produto_combo.currentData()
        self.produto_combo.clear()
        self.produto_combo.addItem("Selecione um produto...", None)
        for produto in selectable_products(self.products):
            self.produto_combo.addItem(
                f"{produto.code} — {produto.name}", produto.code
            )

        if atual is not None:
            indice = self.produto_combo.findData(atual)
            if indice >= 0:
                self.produto_combo.setCurrentIndex(indice)

    def set_suppliers(self, suppliers):
        """Oferece somente fornecedores ativos para novas entradas."""
        selected = self.fornecedor_combo.currentData()
        self._suppliers = tuple(s for s in suppliers if s.active)
        self.fornecedor_combo.clear()
        self.fornecedor_combo.addItem("Selecione um fornecedor...", None)
        for supplier in self._suppliers:
            self.fornecedor_combo.addItem(supplier.name, supplier.supplier_id)
        if selected is not None:
            index = self.fornecedor_combo.findData(selected)
            if index >= 0:
                self.fornecedor_combo.setCurrentIndex(index)
        self._update_supplier_enabled()

    def _update_supplier_enabled(self, *_):
        is_entry = self.especie_combo.currentData() == MovementKind.ENTRADA
        self.fornecedor_combo.setEnabled(is_entry and self._pode_movimentar)

    def set_movements(self, movimentacoes):
        """Redesenha o histórico inteiro a partir das tuplas recebidas."""
        self.movimentacoes = tuple(movimentacoes)
        self._list_state_error = False
        self.load_error_label.setVisible(False)

        for row in range(self.table.rowCount()):
            self.table.removeCellWidget(row, ACTIONS_COLUMN)
        self.table.clearContents()
        self.table.setRowCount(len(self.movimentacoes))

        for row, mov in enumerate(self.movimentacoes):
            produto = QTableWidgetItem(f"{mov[MOV_CODE]} — {mov[MOV_NAME]}")
            produto.setForeground(Qt.blue)
            self.table.setItem(row, 0, produto)
            self.table.setItem(row, 1, QTableWidgetItem(str(mov[MOV_KIND])))
            self.table.setItem(row, 2, QTableWidgetItem(str(mov[MOV_QTY])))
            self.table.setItem(row, 3, QTableWidgetItem(str(mov[MOV_STATUS])))
            self.table.setItem(row, 4, QTableWidgetItem(str(mov[MOV_NOTE] or "—")))
            self.table.setItem(row, 5, QTableWidgetItem(str(mov[MOV_WHEN])))
            supplier_name = str(mov[8]) if len(mov) > 8 else "—"
            self.table.setItem(row, 6, QTableWidgetItem(supplier_name))
            self.table.setCellWidget(row, ACTIONS_COLUMN, self._acoes(mov))

        self.table.setVisible(True)
        self._atualizar_vazio()

    def show_load_error(self, erro):
        """Falha fica NA ÁREA DA LISTA, pelo mesmo motivo da tela de Estoque.

        Diálogo some ao ser fechado e deixa uma tabela vazia indistinguível
        de "não há movimentações".
        """
        self._list_state_error = True
        self.last_load_error = erro
        self.load_error_label.setText(
            f"Não foi possível carregar as movimentações.\n\n{erro}"
        )
        self.load_error_label.setVisible(True)
        self.list_state_label.setVisible(False)
        self.table.setVisible(False)

    def _atualizar_vazio(self):
        vazio = not self.movimentacoes
        if vazio:
            self.list_state_label.setText(
                "Nenhuma movimentação registrada. Lance uma entrada ou saída "
                "acima — o saldo do produto é a soma das confirmadas."
            )
        self.list_state_label.setVisible(vazio)
        self.subtitle.setText(
            "Entradas e saídas que compõem o saldo"
            if vazio else
            f"{len(self.movimentacoes)} movimentação(ões) · só as confirmadas somam"
        )

    # ======================================================
    # AÇÕES
    # ======================================================

    def _acoes(self, mov):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)

        pendente = str(mov[MOV_STATUS]) == MovementStatus.PENDENTE.label
        cancelavel = str(mov[MOV_STATUS]) != MovementStatus.CANCELADA.label

        confirmar = self._botao("fa5s.check", "Confirmar movimentação", "#ECFDF5")
        # Só pendente pode ser confirmada — confirmar duas vezes somaria duas
        # vezes, e é por isso que `fn_confirm_movement` recusa o resto.
        confirmar.setEnabled(pendente and self._pode_movimentar)
        confirmar.clicked.connect(
            lambda _=False, i=mov[MOV_ID]: self.confirm_requested.emit(i)
        )

        cancelar = self._botao("fa5s.ban", "Cancelar movimentação", "#FEF2F2")
        cancelar.setEnabled(cancelavel and self._pode_movimentar)
        cancelar.clicked.connect(
            lambda _=False, i=mov[MOV_ID]: self.cancel_requested.emit(i)
        )

        layout.addWidget(confirmar)
        layout.addWidget(cancelar)
        layout.addStretch()
        return container

    @staticmethod
    def _botao(icone, dica, cor_hover):
        botao = QPushButton()
        botao.setIcon(qta.icon(icone, color="#94A3B8"))
        botao.setFixedSize(28, 28)
        botao.setToolTip(dica)
        botao.setAccessibleName(dica)
        botao.setStyleSheet(
            "QPushButton { background-color: transparent; border: none; }"
            f"QPushButton:hover {{ background-color: {cor_hover}; border-radius: 6px; }}"
        )
        return botao

    def _registrar(self, confirmar: bool):
        """Valida o que a tela sabe e pede. A recusa que vale é do serviço."""
        from stockflow.application.dto.movement_input import MovementInput

        codigo = self.produto_combo.currentData()
        if not codigo:
            self.warning_label.setText("Selecione um produto ativo.")
            return

        especie = self.especie_combo.currentData()
        supplier_id = self.fornecedor_combo.currentData()
        if especie == MovementKind.ENTRADA and not supplier_id:
            self.warning_label.setText("Selecione um fornecedor ativo para a entrada.")
            return

        self.warning_label.setText("")
        self.register_requested.emit(MovementInput(
            product_code=codigo,
            kind=especie,
            quantity=self.quantidade_input.value(),
            note=self.nota_input.text().strip(),
            confirm=confirmar,
            supplier_id=supplier_id if especie == MovementKind.ENTRADA else None,
        ))

    def limpar_formulario(self):
        self.quantidade_input.setValue(1)
        self.nota_input.clear()
        self.fornecedor_combo.setCurrentIndex(0)
        self.warning_label.setText("")

    def mostrar_recusa(self, mensagem):
        self.warning_label.setText(str(mensagem))

    # ======================================================
    # PERMISSÃO
    # ======================================================

    def apply_permission(self, pode_movimentar: bool):
        """Controles visuais do papel. A recusa que vale é do serviço e do banco.

        `fn_register_movement` e as irmãs checam `fn_has_role(ADMIN, STOCK)`
        por conta própria; esconder o botão é cortesia, não controle.
        """
        self._pode_movimentar = bool(pode_movimentar)
        for widget in (self.produto_combo, self.especie_combo,
                       self.quantidade_input, self.nota_input,
                       self.fornecedor_combo,
                       self.registrar_button, self.registrar_confirmar_button):
            widget.setEnabled(self._pode_movimentar)
        # Os botões da tabela nascem habilitados a cada redesenho; refazer as
        # linhas é o que reaplica a permissão neles.
        self.set_movements(self.movimentacoes)
        self._update_supplier_enabled()
