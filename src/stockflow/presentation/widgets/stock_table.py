import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from stockflow.presentation.styles import inventory

ACTIONS_COLUMN = 6


class StockTable(QFrame):
    product_edit_requested = Signal(object)

    def __init__(self, products):
        super().__init__()
        self.setStyleSheet(inventory.TABLE_CARD_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Código", "Produto", "Categoria", "Estoque", "Preço", "Status", "Ações"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setStyleSheet(inventory.TABLE_QSS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        # Os botões de ação só existem dentro de cellWidget; sem esta lista,
        # aplicar a permissão do papel exigiria varrer a tabela por índice de
        # coluna — e qualquer mudança de layout quebraria o controle em
        # silêncio, deixando as ações habilitadas para quem não pode usá-las.
        self.action_buttons = []
        # `edit_buttons` NÃO participa da permissão (quem aplica é
        # `action_buttons`, que inclui editar e excluir). Ela existe para os
        # testes de UI alcançarem o botão de editar de cada linha sem depender
        # do índice da coluna de ações.
        self.edit_buttons = []
        # Última permissão aplicada. A tabela precisa lembrar dela por conta
        # própria: `set_products` destrói os botões e cria outros, e um
        # QPushButton nasce habilitado. Sem esta memória, cada recarga
        # devolveria editar/excluir a quem não pode gravar.
        self._actions_enabled = True
        self.set_products(products)
        self.table.verticalHeader().setDefaultSectionSize(62)
        layout.addWidget(self.table)

    def set_products(self, products):
        """Repovoa a tabela com a lista de tuplas recebida.

        Também é o caminho da primeira montagem, para que recarregar e
        construir sigam exatamente o mesmo código — a tabela não tem como
        divergir do estado inicial.

        O `QTableWidget` é reaproveitado de propósito: `EstoquePage.table` e
        os testes guardam essa referência, e trocar o widget deixaria todos
        apontando para uma tabela fora da tela.
        """
        # `clearContents` apaga os itens, mas não os cellWidget: sem remover
        # os containers de ação antes, eles sobreviveriam à troca de linhas.
        for row in range(self.table.rowCount()):
            self.table.removeCellWidget(row, ACTIONS_COLUMN)
        self.table.clearContents()
        # As listas descrevem botões que acabaram de ser destruídos; mantê-las
        # deixaria `set_actions_enabled` tocando widgets órfãos e os testes
        # lendo o estado da tabela anterior.
        self.action_buttons = []
        self.edit_buttons = []
        self.table.setRowCount(len(products))
        for row, product in enumerate(products):
            for column, value in enumerate(product):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setForeground(Qt.blue)
                self.table.setItem(row, column, item)
            self.table.setCellWidget(row, ACTIONS_COLUMN, self._create_actions(product))
        # Reaplicar é obrigatório, não cosmético: os botões acima são novos e
        # vieram habilitados.
        self.set_actions_enabled(self._actions_enabled)

    def _create_actions(self, product):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        edit = self._action_button("fa5s.pen", "Editar produto", "#EFF6FF")
        edit.clicked.connect(lambda: self.product_edit_requested.emit(product))
        # ATENÇÃO: "Excluir produto" ainda não tem handler — clicar não apaga
        # nada. Ele é desabilitado junto com os demais por `set_actions_enabled`
        # para não prometer uma ação indisponível ao papel. Quem for conectar
        # a exclusão PRECISA passar pelo `ProductService`: apagar direto do
        # dict do catálogo pularia a checagem de permissão da US01.
        delete = self._action_button("fa5s.trash-alt", "Excluir produto", "#FEF2F2")
        layout.addWidget(edit)
        layout.addWidget(delete)
        self.edit_buttons.append(edit)
        self.action_buttons.extend((edit, delete))
        return container

    def set_actions_enabled(self, enabled: bool):
        """Liga/desliga editar e excluir conforme o papel do usuário."""
        self._actions_enabled = enabled
        for button in self.action_buttons:
            button.setEnabled(enabled)

    @staticmethod
    def _action_button(icon, tooltip, hover_color):
        button = QPushButton()
        button.setIcon(qta.icon(icon, color="#94A3B8"))
        button.setFixedSize(28, 28)
        button.setToolTip(tooltip)
        button.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; border: none; }}
            QPushButton:hover {{ background-color: {hover_color}; border-radius: 6px; }}
        """)
        return button
