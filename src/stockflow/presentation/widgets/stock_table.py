import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from stockflow.domain.stock_level import INACTIVE
from stockflow.presentation.styles import inventory

# "Mínimo" vem logo depois de "Estoque": a US03 pede consultar saldo E mínimo,
# e a US04 pede que o alerta devolva os dois. Sem a coluna, o usuário vê
# "Baixo" sem saber baixo em relação a quê.
COLUMNS = ("Código", "Produto", "Categoria", "Estoque", "Mínimo",
           "Preço", "Status", "Ações")

# Derivados de COLUMNS, nunca escritos à mão: a tabela nasceu com sete colunas
# fixas no construtor e oito rótulos, e o rótulo que sobrava era silenciosamente
# descartado — a coluna de Ações sumia e as linhas ficavam sem botão.
ACTIONS_COLUMN = len(COLUMNS) - 1
TEXT_COLUMNS = ACTIONS_COLUMN
STATUS_COLUMN = COLUMNS.index("Status")

# A linha do modelo tem UM campo a mais que as colunas de texto (`active`, que
# decide o rótulo da coluna de situação sem ser coluna própria). Enumerar a
# linha inteira jogaria um booleano dentro da célula de Ações.
ACTIVE_FIELD = TEXT_COLUMNS


class StockTable(QFrame):
    product_edit_requested = Signal(object)
    # A tabela não altera o produto: ela pede. Quem decide é a página, que
    # tem o catálogo compartilhado e sabe refletir a mudança nas outras
    # telas. Alternar aqui dentro deixaria a linha e o catálogo divergirem.
    product_status_toggle_requested = Signal(object)

    def __init__(self, products):
        super().__init__()
        self.setStyleSheet(inventory.TABLE_CARD_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
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
            ativo = self._esta_ativo(product)
            for column in range(min(TEXT_COLUMNS, len(product))):
                value = product[column]
                # Situação de cadastro ganha da situação de estoque na
                # coluna: um produto inativo não é "Crítico", ele está fora
                # de operação. Mostrar "Crítico" aqui mandaria o estoquista
                # repor um item que ninguém pode vender.
                if column == STATUS_COLUMN and not ativo:
                    value = INACTIVE
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setForeground(Qt.blue)
                self.table.setItem(row, column, item)
            self.table.setCellWidget(row, ACTIONS_COLUMN, self._create_actions(product))
        # Reaplicar é obrigatório, não cosmético: os botões acima são novos e
        # vieram habilitados.
        self.set_actions_enabled(self._actions_enabled)

    @staticmethod
    def _esta_ativo(product) -> bool:
        """Situação de cadastro da linha, com ausência tratada como ativa.

        Linhas de 6 campos (a tupla que a tela emitia antes da US04) não
        carregam `active`. Assumir inativo esconderia o catálogo inteiro de
        quem ainda constrói a linha no formato antigo.
        """
        return True if len(product) <= ACTIVE_FIELD else bool(product[ACTIVE_FIELD])

    def _create_actions(self, product):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        edit = self._action_button("fa5s.pen", "Editar produto", "#EFF6FF")
        edit.clicked.connect(lambda: self.product_edit_requested.emit(product))
        # Desativar, não excluir: o produto inativo continua resolvendo a FK
        # das vendas antigas (US02). O ícone de lixeira que ficava aqui não
        # tinha handler nenhum — prometia uma exclusão que não acontecia, e
        # que o banco não oferece: `fn_set_product_active` faz soft-delete.
        ativo = self._esta_ativo(product)
        toggle = self._action_button(
            "fa5s.ban" if ativo else "fa5s.undo",
            "Desativar produto" if ativo else "Reativar produto",
            "#FEF2F2" if ativo else "#ECFDF5",
        )
        toggle.clicked.connect(
            lambda: self.product_status_toggle_requested.emit(product)
        )
        layout.addWidget(edit)
        layout.addWidget(toggle)
        self.edit_buttons.append(edit)
        self.action_buttons.extend((edit, toggle))
        return container

    def set_actions_enabled(self, enabled: bool):
        """Liga/desliga editar e ativar/desativar conforme o papel."""
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
