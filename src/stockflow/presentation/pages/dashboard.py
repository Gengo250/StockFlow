"""Visão operacional do catálogo demonstrativo compartilhado pela janela."""
from collections import Counter

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from stockflow.presentation.styles.dashboard import DASHBOARD_QSS


def label(text, role='muted'):
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setWordWrap(True)
    return widget


def panel(title, description):
    card = QFrame()
    card.setObjectName('dashboardCard')
    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 22, 22, 22)
    layout.setSpacing(14)
    layout.addWidget(label(title, 'sectionTitle'))
    layout.addWidget(label(description))
    return card, layout


def action(text, icon, primary=False):
    button = QPushButton(text)
    button.setObjectName('primaryAction' if primary else 'dashboardAction')
    button.setIcon(qta.icon(icon, color='white' if primary else '#2563EB'))
    button.setCursor(Qt.PointingHandCursor)
    button.setMinimumHeight(42)
    return button


class DashboardPage(QWidget):
    page_requested = Signal(str)
    product_requested = Signal(str)
    new_product_requested = Signal()

    def __init__(self, products):
        super().__init__()
        self.products = products
        self.setObjectName('dashboardPage')
        self.setStyleSheet(DASHBOARD_QSS)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)
        content = QWidget()
        content.setObjectName('dashboardContent')
        self.layout = QVBoxLayout(content)
        self.layout.setContentsMargins(26, 24, 26, 24)
        self.layout.setSpacing(20)
        self.layout.addWidget(label('Dashboard', 'pageTitle'))
        self.layout.addWidget(label('Visão geral do estoque · Dados demonstrativos'))

        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(14)
        self.metric_cards = []
        self.metric_values = []
        for title, description, icon in (
            ('Produtos cadastrados', 'Itens no catálogo', 'fa5s.box'),
            ('Unidades em estoque', 'Saldo total do catálogo', 'fa5s.cubes'),
            ('Precisam de atenção', 'Estoque baixo ou crítico', 'fa5s.exclamation-triangle'),
            ('Categorias', 'Grupos de produtos', 'fa5s.layer-group'),
        ):
            card, layout = panel(title, description)
            badge = QLabel()
            badge.setPixmap(qta.icon(icon, color='#2563EB').pixmap(22, 22))
            layout.insertWidget(0, badge)
            value = label('0', 'metricValue')
            layout.insertWidget(2, value)
            self.metric_cards.append(card)
            self.metric_values.append(value)
        self.layout.addLayout(self.metrics_grid)

        self.body_grid = QGridLayout()
        self.body_grid.setSpacing(20)
        self.alert_card, alerts = panel('Atenção ao estoque', 'Priorize os produtos com menor disponibilidade.')
        self.alert_rows = QVBoxLayout()
        self.alert_rows.setSpacing(8)
        alerts.addLayout(self.alert_rows)
        alerts.addStretch()
        self.inventory_button = action('Ver estoque completo', 'fa5s.arrow-right')
        self.inventory_button.clicked.connect(lambda: self.page_requested.emit('estoque'))
        alerts.addWidget(self.inventory_button)
        self.category_card, categories = panel('Estoque por categoria', 'Participação no total de unidades disponíveis.')
        self.category_rows = QVBoxLayout()
        self.category_rows.setSpacing(18)
        categories.addLayout(self.category_rows)
        categories.addStretch()
        self.catalog_button = action('Explorar catálogo', 'fa5s.arrow-right')
        self.catalog_button.clicked.connect(lambda: self.page_requested.emit('produtos'))
        categories.addWidget(self.catalog_button)
        self.layout.addLayout(self.body_grid)

        quick_card, quick = panel('Ações rápidas', 'Acesse as tarefas do dia a dia.')
        self.actions_grid = QGridLayout()
        self.actions_grid.setSpacing(12)
        self.new_product_button = action('Novo produto', 'fa5s.plus', True)
        self.new_product_button.clicked.connect(self.new_product_requested.emit)
        self.movements_button = action('Movimentações', 'fa5s.exchange-alt')
        self.movements_button.clicked.connect(lambda: self.page_requested.emit('movimentacoes'))
        self.actions_grid.addWidget(self.new_product_button, 0, 0)
        self.actions_grid.addWidget(self.movements_button, 0, 1)
        quick.addLayout(self.actions_grid)
        self.layout.addWidget(quick_card)
        self.layout.addStretch()
        self.scroll.setWidget(content)
        self._columns = None
        self.refresh()
        self._reflow()

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh(self):
        products = list(self.products.values())
        attention = sorted(
            (p for p in products if p.stock_status in ('Baixo', 'Crítico')),
            key=lambda p: (p.stock_status != 'Crítico', int(p.stock), p.name),
        )
        units = sum(int(p.stock) for p in products)
        counts = Counter()
        for product in products:
            counts[product.category] += int(product.stock)
        for widget, value in zip(self.metric_values, (len(products), units, len(attention), len(counts))):
            widget.setText(str(value))
        self._clear(self.alert_rows)
        self.alert_buttons = []
        for product in attention:
            row = action(f'{product.name}\n{product.code} · {product.stock} un. · {product.stock_status}',
                         'fa5s.exclamation-circle')
            row.setObjectName('stockAlert')
            row.setProperty('critical', product.stock_status == 'Crítico')
            row.setMinimumHeight(70)
            row.setToolTip(f'Ver detalhes de {product.name}')
            row.clicked.connect(lambda checked=False, code=product.code: self.product_requested.emit(code))
            self.alert_rows.addWidget(row)
            self.alert_buttons.append(row)
        if not attention:
            self.alert_rows.addWidget(label(
                'Nenhum produto cadastrado. Comece adicionando um produto.' if not products
                else 'Nenhum produto com estoque baixo ou crítico.', 'emptyState'))
        self._clear(self.category_rows)
        for category, quantity in counts.most_common():
            group = QWidget()
            layout = QVBoxLayout(group)
            layout.setContentsMargins(0, 0, 0, 0)
            line = QHBoxLayout()
            line.addWidget(label(category, 'categoryName'), 1)
            line.addWidget(label(f'{quantity} un.', 'categoryName'))
            layout.addLayout(line)
            bar = QProgressBar()
            bar.setRange(0, max(units, 1))
            bar.setValue(quantity)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar.setAccessibleName(f'{category}: {quantity} de {units} unidades')
            layout.addWidget(bar)
            self.category_rows.addWidget(group)
        if not counts:
            self.category_rows.addWidget(label('As categorias aparecerão quando houver produtos.', 'emptyState'))

    def _reflow(self):
        columns = 4 if self.width() >= 1000 else 2 if self.width() >= 560 else 1
        if columns == self._columns:
            return
        self._columns = columns
        while self.metrics_grid.count():
            self.metrics_grid.takeAt(0)
        for column in range(4):
            self.metrics_grid.setColumnStretch(column, int(column < columns))
        for index, card in enumerate(self.metric_cards):
            self.metrics_grid.addWidget(card, index // columns, index % columns)
        self.body_grid.removeWidget(self.alert_card)
        self.body_grid.removeWidget(self.category_card)
        wide = columns == 4
        self.body_grid.addWidget(self.alert_card, 0, 0)
        self.body_grid.addWidget(self.category_card, 0 if wide else 1, 1 if wide else 0)
        self.body_grid.setColumnStretch(0, 3)
        self.body_grid.setColumnStretch(1, 2 if wide else 0)
        self.actions_grid.removeWidget(self.movements_button)
        self.actions_grid.addWidget(self.movements_button, int(columns == 1), int(columns != 1))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
