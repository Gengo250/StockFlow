import qtawesome as qta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from stockflow.presentation.styles.products import PRODUCTS_QSS
from stockflow.presentation.widgets.product_card import ProductCard


class ProductsPage(QWidget):
    product_requested = Signal(str)

    def __init__(self, products):
        super().__init__()
        self.products = products
        self.setObjectName('productsPage')
        self.setStyleSheet(PRODUCTS_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(4)
        title = QLabel('Catálogo de Produtos')
        title.setObjectName('pageTitle')
        heading.addWidget(title)
        subtitle = QLabel('Gerencie seu catálogo completo · Dados demonstrativos')
        subtitle.setObjectName('muted')
        subtitle.setWordWrap(True)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        self.new_product_button = QPushButton('Novo Produto')
        self.new_product_button.setObjectName('newProductButton')
        self.new_product_button.setIcon(qta.icon('fa5s.plus', color='white'))
        header.addWidget(self.new_product_button, 0, Qt.AlignTop)
        layout.addLayout(header)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Buscar por nome, identificador ou categoria...')
        self.search_input.setAccessibleName('Buscar no catálogo de produtos')
        self.search_input.addAction(qta.icon('fa5s.search', color='#94A3B8'), QLineEdit.LeadingPosition)
        layout.addWidget(self.search_input)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        self.grid = QGridLayout(content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        self.grid.setAlignment(Qt.AlignTop)
        self.cards = {}
        self._layout_state = None
        self._cards_container = content
        self._build_cards()
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)
        self.empty_message = QLabel('Nenhum produto encontrado. Tente outra busca.')
        self.empty_message.setObjectName('muted')
        self.empty_message.setWordWrap(True)
        layout.addWidget(self.empty_message)
        self.search_input.textChanged.connect(self._arrange_cards)
        self._arrange_cards()

    def _build_cards(self):
        """Cria um card por produto do catálogo atual."""
        maximum = max(
            (int(product.stock) for product in self.products.values()), default=1
        )
        for code, product in self.products.items():
            card = ProductCard(product, max(maximum, 1))
            card.setParent(self._cards_container)
            card.clicked.connect(
                lambda checked=False, key=code: self.product_requested.emit(key)
            )
            self.cards[code] = card

    def reload_products(self, products=None):
        """Reconstrói os cards a partir do catálogo.

        Os cards são widgets montados com os valores do produto no momento da
        criação; não existe caminho de atualização dentro do `ProductCard`.
        Então refletir uma gravação é refazê-los. A busca digitada é
        preservada de propósito: o usuário que salvou um produto no meio de
        uma pesquisa não deve perder o filtro — `_arrange_cards` relê o texto
        que já está no campo.
        """
        if products is not None:
            self.products = products
        for card in self.cards.values():
            # setParent(None) tira o card do grid; deleteLater devolve a
            # memória sem derrubar um sinal que ainda esteja em curso.
            card.setParent(None)
            card.deleteLater()
        self.cards = {}
        self._build_cards()
        # O layout anterior descrevia cards que não existem mais: sem zerar o
        # estado, `_arrange_cards` acharia que não há nada a redesenhar.
        self._layout_state = None
        self._arrange_cards()

    def _arrange_cards(self):
        columns = max(1, min(3, (self.width() - 52 + 16) // 306))
        query = self.search_input.text().strip().casefold()
        visible_codes = tuple(
            code for code in self.cards
            if (product := self.products.get(code)) is not None
            and query in f'{product.code} {product.name} {product.category}'.casefold()
        )
        state = (columns, visible_codes)
        if state == self._layout_state:
            return
        self._layout_state = state
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(3):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        visible_set = set(visible_codes)
        for code, card in self.cards.items():
            card.setVisible(code in visible_set)
        for index, code in enumerate(visible_codes):
            self.grid.addWidget(self.cards[code], index // columns, index % columns)
        self.empty_message.setVisible(not visible_codes)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange_cards()
