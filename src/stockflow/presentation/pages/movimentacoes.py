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
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QBoxLayout, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QScrollArea, QVBoxLayout, QWidget,
)

from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.movement_status import MovementStatus
from stockflow.presentation.styles import inventory
from stockflow.presentation.widgets.searchable_combo import SearchableComboBox

COLUMNS = ("Produto", "Espécie", "Quantidade", "Situação", "Observação",
           "Quando", "Fornecedor / Cliente", "Ações")
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

    new_party_requested = Signal()
    register_requested = Signal(object)     # MovementInput
    confirm_requested = Signal(str)         # id da movimentação
    cancel_requested = Signal(str)

    def __init__(self, products=None):
        super().__init__()
        self.setObjectName("movimentacoesPage")
        self.setStyleSheet("""
            QWidget#movimentacoesPage { background: #F0F5FF; }
            QFrame#movementCard { background: white; border: 1px solid #DBEAFE; border-radius: 14px; }
            QLabel { background: transparent; border: none; color: #334155; }
            QComboBox, QLineEdit, QSpinBox { background: white; color: #334155; border: 1px solid #CBDFFF; border-radius: 9px; padding: 8px; font-size: 12px; }
            QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 1px solid #2563EB; }
            QComboBox::drop-down { border: none; width: 22px; }
            QPushButton:disabled { color: #94A3B8; }
        """)

        # O MESMO dict da janela, nunca uma cópia. É essa identidade que faz
        # um produto desativado no Estoque sair da oferta aqui na hora — a
        # mesma razão pela qual Vendas e Estoque o compartilham. Copiar
        # congelaria a oferta no estado em que a janela abriu.
        self.products = {} if products is None else products
        self.movimentacoes = ()
        self._pode_movimentar = True
        self._suppliers = ()
        self._can_create_supplier = True
        self._can_create_client = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)
        layout.addLayout(self._create_header())
        layout.addLayout(self._create_summary())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        content = QWidget()
        self.body_layout = QBoxLayout(QBoxLayout.LeftToRight, content)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(22)
        self.form_card = self._create_form()
        self.form_card.setMinimumWidth(280)
        self.body_layout.addWidget(self.form_card, 3, Qt.AlignTop)
        self.body_layout.addWidget(self._create_table(), 7, Qt.AlignTop)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

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
        titulo = QLabel("Movimentação de Produtos")
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

    @staticmethod
    def _card_heading(layout, title, subtitle):
        heading = QLabel(title)
        heading.setStyleSheet("color: #0F172A; font-size: 15px; font-weight: 600;")
        description = QLabel(subtitle)
        description.setStyleSheet("color: #8DA2C4; font-size: 11px;")
        layout.addWidget(heading)
        layout.addWidget(description)

    def _create_summary(self):
        row = QHBoxLayout()
        row.setSpacing(14)
        self.summary_values = []
        for title, icon, color, background in (
            ("Unidades de entrada confirmadas", "fa5s.arrow-down", "#009B72", "#ECFDF5"),
            ("Unidades de saída confirmadas", "fa5s.arrow-up", "#2563EB", "#EFF6FF"),
            ("Movimentações", "fa5s.exchange-alt", "#8B36FF", "#F5F3FF"),
        ):
            card = QFrame()
            card.setObjectName("movementCard")
            line = QHBoxLayout(card)
            line.setContentsMargins(18, 18, 18, 18)
            badge = QLabel()
            badge.setFixedSize(40, 40)
            badge.setAlignment(Qt.AlignCenter)
            badge.setPixmap(qta.icon(icon, color=color).pixmap(16, 16))
            badge.setStyleSheet(f"background: {background}; border-radius: 12px;")
            line.addWidget(badge)
            texts = QVBoxLayout()
            value = QLabel("0")
            value.setStyleSheet(f"color: {color}; font-size: 23px; font-weight: 600;")
            label = QLabel(title)
            label.setWordWrap(True)
            label.setStyleSheet("color: #647C9E; font-size: 11px;")
            texts.addWidget(value)
            texts.addWidget(label)
            line.addLayout(texts, 1)
            row.addWidget(card, 1)
            self.summary_values.append(value)
        return row

    def _create_form(self):
        card = QFrame()
        card.setObjectName("movementCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 20, 18, 18)
        layout.setSpacing(12)
        self._card_heading(layout, "Nova movimentação", "Preencha os dados da operação")
        self.especie_combo = QComboBox(card)
        for kind in MovementKind:
            self.especie_combo.addItem(kind.label, kind)
        self.especie_combo.hide()
        tabs = QFrame()
        tabs.setStyleSheet("QFrame { background: #EFF6FF; border: none; border-radius: 11px; }")
        tab_layout = QHBoxLayout(tabs)
        tab_layout.setContentsMargins(4, 4, 4, 4)
        self.kind_buttons = []
        for index, kind in enumerate(MovementKind):
            button = QPushButton(kind.label)
            button.setCheckable(True)
            button.setFixedHeight(36)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("QPushButton { border: none; background: transparent; color: #647C9E; border-radius: 9px; font-weight: 600; } QPushButton:checked { background: white; color: #2563EB; }")
            button.clicked.connect(lambda checked=False, i=index: self.especie_combo.setCurrentIndex(i))
            tab_layout.addWidget(button)
            self.kind_buttons.append(button)
        layout.addWidget(tabs)
        self.produto_combo = SearchableComboBox("Busque por nome ou código...")
        self.produto_combo.setAccessibleName("Produto da movimentação")
        self.quantidade_input = QSpinBox()
        self.quantidade_input.setRange(1, 999999)
        self.quantidade_input.setButtonSymbols(QSpinBox.NoButtons)
        self.quantidade_input.setAccessibleName("Quantidade")
        self.fornecedor_combo = SearchableComboBox("Busque um fornecedor...")
        self.fornecedor_combo.setAccessibleName("Fornecedor da entrada")
        self.fornecedor_combo.addItem("", None)
        self.cliente_combo = SearchableComboBox("Busque um cliente...")
        self.cliente_combo.setAccessibleName("Cliente da saída")
        self.cliente_combo.addItem("", None)
        self.party_label = QLabel("Fornecedor")
        self.new_party_button = QPushButton("Cadastrar novo fornecedor")
        self.new_party_button.setFixedHeight(32)
        self.new_party_button.setCursor(Qt.PointingHandCursor)
        self.new_party_button.setStyleSheet("QPushButton { color: #2563EB; background: #EFF6FF; border: none; border-radius: 8px; text-align: left; padding: 6px; }")
        self.new_party_button.clicked.connect(self.new_party_requested.emit)
        self.nota_input = QLineEdit()
        self.nota_input.setPlaceholderText("Adicione detalhes da movimentação...")
        for title, widget in (("Produto", self.produto_combo), ("Quantidade", self.quantidade_input), ("Fornecedor", self.fornecedor_combo), ("Observação", self.nota_input)):
            label = self.party_label if widget is self.fornecedor_combo else QLabel(title)
            label.setStyleSheet("font-size: 12px; color: #475569;")
            layout.addWidget(label)
            widget.setFixedHeight(40)
            layout.addWidget(widget)
            if widget is self.fornecedor_combo:
                self.cliente_combo.setFixedHeight(40)
                layout.addWidget(self.cliente_combo)
                layout.addWidget(self.new_party_button)
        self.registrar_confirmar_button = QPushButton()
        self.registrar_confirmar_button.setFixedHeight(42)
        self.registrar_confirmar_button.clicked.connect(lambda: self._registrar(confirmar=True))
        self.registrar_button = QPushButton("Salvar como pendente")
        self.registrar_button.setFixedHeight(36)
        self.registrar_button.setStyleSheet("QPushButton { background: white; border: 1px solid #DBEAFE; border-radius: 9px; color: #64748B; }")
        self.registrar_button.clicked.connect(lambda: self._registrar(confirmar=False))
        layout.addWidget(self.registrar_confirmar_button)
        layout.addWidget(self.registrar_button)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #EF4444; font-size: 12px;")
        layout.addWidget(self.warning_label)
        self.especie_combo.currentIndexChanged.connect(self._update_supplier_enabled)
        self._update_supplier_enabled()
        return card

    def resizeEvent(self, event):
        super().resizeEvent(event)
        wide = self.width() >= 1000
        self.body_layout.setDirection(QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom)
        self.form_card.setMinimumWidth(320 if wide else 280)
        self.form_card.setMaximumWidth(345 if wide else 16777215)

    def _create_table(self):
        card = QFrame()
        card.setObjectName("movementCard")
        fora = QVBoxLayout(card)
        fora.setContentsMargins(0, 0, 0, 0)

        heading = QVBoxLayout()
        heading.setContentsMargins(18, 20, 18, 16)
        self._card_heading(heading, "Movimentações recentes", "Histórico de entradas e saídas")
        fora.addLayout(heading)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setStyleSheet(inventory.TABLE_QSS)
        cabecalho = self.table.horizontalHeader()
        cabecalho.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        cabecalho.setMinimumSectionSize(65)
        cabecalho.setStyleSheet("QHeaderView { background-color: #F8FBFF; }")
        cabecalho.setSectionResizeMode(QHeaderView.ResizeToContents)
        for column in (0, 4, 6):
            cabecalho.setSectionResizeMode(column, QHeaderView.Stretch)
        cabecalho.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 90)
        cabecalho.moveSection(cabecalho.visualIndex(1), 0)
        self.table.setHorizontalHeaderItem(1, QTableWidgetItem("Tipo"))
        self.table.setHorizontalHeaderItem(2, QTableWidgetItem("Qtd."))
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.setMinimumHeight(340)
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
        self.produto_combo.addItem("", None)
        for produto in self.products.values():
            if not produto.active:
                continue
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
        self.fornecedor_combo.addItem("", None)
        for supplier in sorted(self._suppliers, key=lambda item: item.name.casefold()):
            self.fornecedor_combo.addItem(supplier.name, supplier.supplier_id)
        if selected is not None:
            index = self.fornecedor_combo.findData(selected)
            if index >= 0:
                self.fornecedor_combo.setCurrentIndex(index)
        self._update_supplier_enabled()

    def set_clients(self, clients):
        selected = self.cliente_combo.currentData()
        self.cliente_combo.clear()
        self.cliente_combo.addItem("", None)
        for client in sorted(clients, key=lambda item: item.name.casefold()):
            if client.active:
                self.cliente_combo.addItem(client.name, client.client_id)
        if selected is not None:
            index = self.cliente_combo.findData(selected)
            if index >= 0:
                self.cliente_combo.setCurrentIndex(index)

    def set_party_permissions(self, suppliers, clients):
        self._can_create_supplier = suppliers
        self._can_create_client = clients
        self._update_supplier_enabled()

    def _update_supplier_enabled(self, *_):
        is_entry = self.especie_combo.currentData() == MovementKind.ENTRADA
        self.fornecedor_combo.setVisible(is_entry)
        self.cliente_combo.setVisible(not is_entry)
        self.cliente_combo.setEnabled(not is_entry and self._pode_movimentar)
        self.party_label.setText("Fornecedor" if is_entry else "Cliente")
        self.new_party_button.setText("Cadastrar novo fornecedor" if is_entry else "Cadastrar novo cliente")
        can_create = self._can_create_supplier if is_entry else self._can_create_client
        self.new_party_button.setEnabled(can_create and self._pode_movimentar)
        self.fornecedor_combo.setEnabled(is_entry and self._pode_movimentar)
        self.fornecedor_combo.setToolTip("Selecione o fornecedor da entrada." if is_entry else "Fornecedor se aplica somente a entradas.")
        for index, button in enumerate(self.kind_buttons):
            button.setChecked(index == self.especie_combo.currentIndex())
            button.setEnabled(self._pode_movimentar)
        self.registrar_confirmar_button.setText("Registrar entrada" if is_entry else "Registrar saída")
        self.registrar_confirmar_button.setToolTip("Registra e confirma a movimentação, atualizando o saldo.")
        color = "#009B72" if is_entry else "#2563EB"
        self.registrar_confirmar_button.setStyleSheet(f"QPushButton {{ background: {color}; color: white; border: none; border-radius: 10px; font-weight: 600; }} QPushButton:disabled {{ background: #CBD5E1; }}")

    def set_movements(self, movimentacoes):
        """Redesenha o histórico inteiro a partir das tuplas recebidas."""
        self.movimentacoes = tuple(movimentacoes)
        confirmed = [m for m in self.movimentacoes if str(m[MOV_STATUS]) == MovementStatus.CONFIRMADA.label]
        for label, kind in zip(self.summary_values[:2], MovementKind):
            label.setText(str(sum(int(m[MOV_QTY]) for m in confirmed if str(m[MOV_KIND]) == kind.label)))
        self.summary_values[2].setText(str(len(self.movimentacoes)))
        self._list_state_error = False
        self.load_error_label.setVisible(False)

        for row in range(self.table.rowCount()):
            self.table.removeCellWidget(row, ACTIONS_COLUMN)
            self.table.removeCellWidget(row, 1)
        self.table.clearContents()
        self.table.setRowCount(len(self.movimentacoes))

        for row, mov in enumerate(self.movimentacoes):
            produto = QTableWidgetItem(f"{mov[MOV_CODE]} — {mov[MOV_NAME]}")
            produto.setForeground(QColor("#334155"))
            produto.setToolTip(produto.text())
            self.table.setItem(row, 0, produto)
            self.table.setItem(row, 1, QTableWidgetItem(str(mov[MOV_KIND])))
            self.table.setItem(row, 2, QTableWidgetItem(str(mov[MOV_QTY])))
            self.table.setItem(row, 3, QTableWidgetItem(str(mov[MOV_STATUS])))
            self.table.setItem(row, 4, QTableWidgetItem(str(mov[MOV_NOTE] or "—")))
            self.table.setItem(row, 5, QTableWidgetItem(str(mov[MOV_WHEN])))
            supplier_name = str(mov[8]) if len(mov) > 8 else "—"
            self.table.setItem(row, 6, QTableWidgetItem(supplier_name))
            self.table.setCellWidget(row, ACTIONS_COLUMN, self._acoes(mov))
            is_entry = str(mov[MOV_KIND]) == MovementKind.ENTRADA.label
            color, background = ("#009B72", "#ECFDF5") if is_entry else ("#2563EB", "#EFF6FF")
            badge_container = QWidget()
            badge_container.setStyleSheet("background: white;")
            badge_layout = QHBoxLayout(badge_container)
            badge_layout.setContentsMargins(10, 16, 10, 16)
            badge = QLabel(str(mov[MOV_KIND]))
            badge.setFixedSize(60, 22)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(f"color: {color}; background: {background}; border-radius: 10px; font-size: 11px; font-weight: 600;")
            badge_layout.addWidget(badge)
            self.table.setCellWidget(row, 1, badge_container)
            quantity = self.table.item(row, 2)
            quantity.setText(f"{'+' if is_entry else '−'}{mov[MOV_QTY]}")
            quantity.setForeground(QColor(color))
            font = quantity.font()
            font.setBold(True)
            quantity.setFont(font)
            status_color = STATUS_COLORS.get(str(mov[MOV_STATUS]), ("#64748B", "#FFFFFF"))[0]
            self.table.item(row, 3).setForeground(QColor(status_color))
            for column in (4, 5, 6):
                self.table.item(row, column).setToolTip(self.table.item(row, column).text())

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
                "no formulário — o saldo do produto é a soma das confirmadas."
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
        if not codigo or self.produto_combo.currentText() != self.produto_combo.itemText(self.produto_combo.currentIndex()):
            self.warning_label.setText("Selecione um produto ativo.")
            return

        especie = self.especie_combo.currentData()
        supplier_id = self.fornecedor_combo.currentData()
        party_combo = self.fornecedor_combo if especie == MovementKind.ENTRADA else self.cliente_combo
        if party_combo.currentText() != party_combo.itemText(party_combo.currentIndex()):
            self.warning_label.setText("Escolha um cadastro da lista ou use o botão de cadastrar.")
            return
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
            client_id=self.cliente_combo.currentData() if especie == MovementKind.SAIDA else None,
        ))

    def limpar_formulario(self):
        self.quantidade_input.setValue(1)
        self.nota_input.clear()
        self.fornecedor_combo.setCurrentIndex(0)
        self.cliente_combo.setCurrentIndex(0)
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
