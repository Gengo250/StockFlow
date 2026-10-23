"""Indicadores da empresa e planejamento de reposição (H31)."""

from stockflow.presentation.styles import design_system as ds

from datetime import datetime
from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from stockflow.domain.replenishment import suggest_replenishment
from stockflow.presentation.workers import PageLoader
from stockflow.presentation.styles import inventory
from stockflow.presentation.pages.reports import money
from stockflow.presentation.widgets.form_fields import _card, _card_header, _line_edit


class DashboardPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, products, sales, clients):
        super().__init__()
        self.loader = PageLoader(self)
        self.read_products = products.list_all
        self.products, self.sales, self.clients = products, sales, clients
        self.suggestions = []
        self._loaded = False
        self.setObjectName('dashboardPage')
        self.setStyleSheet(ds.page_qss("dashboardPage"))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName('dashboardContent')
        content.setStyleSheet(ds.page_qss("dashboardContent"))
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN)
        layout.setSpacing(ds.SECTION_GAP)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        title = QLabel('Visão geral')
        title.setStyleSheet(inventory.TITLE_QSS)
        subtitle = QLabel('Acompanhe os resultados e os produtos que precisam de reposição.')
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(inventory.SUBTITLE_QSS)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles, 1)
        self.refresh_button = QPushButton('Atualizar resumo')
        self.refresh_button.setIcon(qta.icon('fa5s.sync-alt', color='#475569'))
        self.refresh_button.setStyleSheet(inventory.FILTER_QSS)
        self.refresh_button.setFixedHeight(ds.CONTROL_HEIGHT)
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)
        heading.addWidget(self.refresh_button)
        layout.addLayout(heading)

        metrics = QHBoxLayout()
        self.metric_values = []
        self.metric_details = []
        for index, (caption, icon) in enumerate((
            ('Produtos ativos', 'fa5s.boxes'), ('Reposição necessária', 'fa5s.exclamation-triangle'),
            ('Vendas registradas', 'fa5s.chart-line'), ('Clientes ativos', 'fa5s.users'),
        )):
            card = _card(f'dashboardMetric{index}')
            card.layout().setContentsMargins(18, 16, 18, 16)
            card.layout().setSpacing(8)
            top = QHBoxLayout()
            label = QLabel(caption)
            label.setWordWrap(True)
            label.setStyleSheet('color: #64748B; font-size: 12px;')
            top.addWidget(label, 1)
            badge = QLabel()
            badge.setPixmap(qta.icon(icon, color='#2563EB').pixmap(18, 18))
            top.addWidget(badge)
            value = QLabel('—')
            value.setStyleSheet(ds.METRIC_QSS)
            detail = QLabel('Aguardando dados')
            detail.setWordWrap(True)
            detail.setStyleSheet('color: #64748B; font-size: 12px;')
            card.layout().addLayout(top)
            card.layout().addWidget(value)
            card.layout().addWidget(detail)
            self.metric_values.append(value)
            self.metric_details.append(detail)
            metrics.addWidget(card, 1)
        layout.addLayout(metrics)

        card = _card('replenishmentCard')
        content = card.layout()
        content.addLayout(_card_header('fa5s.truck-loading', 'Sugestões de reposição', 'Produtos ativos no mínimo ou abaixo dele, priorizados por criticidade.'))
        rule = QLabel('Meta: atingir a faixa normal (120% do mínimo, arredondado para cima; pelo menos 1 unidade). As sugestões não geram compras automaticamente.')
        rule.setWordWrap(True)
        rule.setStyleSheet('color: #64748B; font-size: 12px;')
        content.addWidget(rule)
        self.search_input = _line_edit('Buscar código ou produto…')
        self.search_input.setAccessibleName('Buscar sugestões de reposição')
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_suggestions)
        content.addWidget(self.search_input)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Código', 'Produto', 'Situação', 'Saldo', 'Mínimo', 'Meta', 'Repor'])
        self.table.setStyleSheet(inventory.TABLE_QSS)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(180)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(ds.ROW_HEIGHT)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        content.addWidget(self.table, 1)
        self.empty_label = QLabel('Atualize para consultar as sugestões de reposição.')
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(inventory.LIST_STATE_QSS)
        content.addWidget(self.empty_label)
        self.result_count = QLabel()
        self.result_count.setStyleSheet('color: #64748B; font-size: 12px;')
        content.addWidget(self.result_count)
        layout.addWidget(card, 1)

        footer = QHBoxLayout()
        self.summary = QLabel('Aguardando atualização')
        self.summary.setTextFormat(Qt.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet('color: #64748B; font-size: 12px;')
        footer.addWidget(self.summary, 1)
        for caption, destination in (('Consultar estoque', 'estoque'), ('Ver relatórios', 'relatorios')):
            button = QPushButton(caption)
            button.setStyleSheet(inventory.FILTER_QSS)
            button.setFixedHeight(40)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, key=destination: self.navigate_requested.emit(key))
            footer.addWidget(button)
        layout.addLayout(footer)

    def refresh(self):
        self.refresh_button.setEnabled(False)
        self.summary.setText('Atualizando indicadores…')
        self.loader.load(
            lambda: (list(self.read_products()), list(self.sales.list_all()),
                     list(self.clients.list_all())),
            self._loaded_summary, self._load_failed,
        )

    def _loaded_summary(self, result):
        products, sales, clients = result
        suggestions = suggest_replenishment(products)
        active = [product for product in products if product.active]
        total = sum((Decimal(str(sale['total'])) for sale in sales), Decimal(0))
        values = (len(active), len(suggestions), money(total), sum(client.active for client in clients))
        details = (f'{sum(int(product.stock) for product in active)} unidades em estoque ativo',
                   f'{sum(item.status == "Crítico" for item in suggestions)} produtos sem estoque',
                   f'{len(sales)} vendas · todo o histórico', f'{len(clients)} clientes cadastrados')
        for label, value, detail_label, detail in zip(self.metric_values, values, self.metric_details, details):
            label.setText(str(value))
            detail_label.setText(detail)
        self.suggestions = suggestions
        self._loaded = True
        self._render_suggestions()
        self.summary.setText('Atualizado em ' + datetime.now().strftime('%d/%m/%Y às %H:%M'))
        self.refresh_button.setEnabled(True)

    def _load_failed(self, error):
        self._loaded = False
        self.suggestions = []
        self.table.setRowCount(0)
        for label, detail in zip(self.metric_values, self.metric_details):
            label.setText('—')
            detail.setText('Dados indisponíveis')
        self.empty_label.setText('Não foi possível consultar a reposição. Tente atualizar novamente.')
        self.empty_label.show()
        self.result_count.clear()
        self.summary.setText(f'Não foi possível atualizar o resumo: {error}')
        self.refresh_button.setEnabled(True)

    def _render_suggestions(self):
        self.table.setRowCount(len(self.suggestions))
        for row, suggestion in enumerate(self.suggestions):
            values = (suggestion.code, suggestion.name, suggestion.status, suggestion.stock,
                      suggestion.minimum, suggestion.target, suggestion.quantity)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column >= 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if column == 2:
                    item.setForeground(QColor('#B91C1C' if value == 'Crítico' else '#B45309'))
                self.table.setItem(row, column, item)
        self._filter_suggestions()

    def _filter_suggestions(self, *_):
        if not self._loaded:
            return
        query = self.search_input.text().strip().casefold()
        visible = 0
        for row, item in enumerate(self.suggestions):
            matches = query in f'{item.code} {item.name}'.casefold()
            self.table.setRowHidden(row, not matches)
            visible += matches
        self.empty_label.setText('Nenhum produto corresponde à busca.' if query else 'Nenhum produto precisa de reposição pelos mínimos configurados.')
        self.empty_label.setVisible(visible == 0)
        self.result_count.setText(f'{visible} de {len(self.suggestions)} sugestões · Produtos sem mínimo configurado não entram nesta lista')
