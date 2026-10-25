"""Consulta e exportação dos relatórios da empresa atual."""

from stockflow.presentation.styles import design_system as ds

import csv
from datetime import datetime
from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.presentation.workers import PageLoader
from stockflow.presentation.styles import inventory
from stockflow.presentation.widgets.form_fields import _card, _combo, _field, _line_edit


def money(value):
    return 'R$ ' + f'{value:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


class ReportsPage(QWidget):
    def __init__(self, products, sales):
        super().__init__()
        self.loader = PageLoader(self)
        self.read_products = products.list_all
        self.products, self.sales = products, sales
        self.rows, self.headers, self._all_rows = [], [], []
        self._loaded = False
        self.setObjectName('reportsPage')
        self.setStyleSheet(ds.page_qss("reportsPage"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN)
        layout.setSpacing(ds.SECTION_GAP)
        layout.addLayout(self._header())
        layout.addLayout(self._summary())
        layout.addWidget(self._filters())
        layout.addWidget(self._results(), 1)
        self.error = QLabel()
        self.error.setTextFormat(Qt.PlainText)
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        self.kind.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self._apply_filters)
        self.status.currentIndexChanged.connect(self._apply_filters)

    def _header(self):
        row = QHBoxLayout()
        text = QVBoxLayout()
        title = QLabel('Relatórios')
        title.setStyleSheet(inventory.TITLE_QSS)
        subtitle = QLabel('Consulte os resultados e exporte os dados da sua operação.')
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(inventory.SUBTITLE_QSS)
        text.addWidget(title)
        text.addWidget(subtitle)
        row.addLayout(text, 1)
        self.refresh_button = QPushButton('Atualizar')
        self.refresh_button.setIcon(qta.icon('fa5s.sync-alt', color='#475569'))
        self.refresh_button.setStyleSheet(inventory.FILTER_QSS)
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button = QPushButton('Exportar CSV')
        self.export_button.setIcon(qta.icon('fa5s.download', color='white'))
        self.export_button.setStyleSheet(inventory.NEW_BUTTON_QSS)
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._choose_export)
        for button in (self.refresh_button, self.export_button):
            button.setFixedHeight(ds.CONTROL_HEIGHT)
            button.setCursor(Qt.PointingHandCursor)
            row.addWidget(button)
        return row

    def _summary(self):
        row = QHBoxLayout()
        row.setSpacing(14)
        self.metrics = []
        for index, icon in enumerate(('fa5s.file-alt', 'fa5s.chart-bar', 'fa5s.check-circle')):
            card = _card(f'reportMetric{index}')
            card.layout().setContentsMargins(18, 14, 18, 14)
            card.layout().setSpacing(6)
            caption = QLabel()
            caption.setStyleSheet('color: #64748B; font-size: 12px;')
            heading = QHBoxLayout()
            heading.addWidget(caption, 1)
            badge = QLabel()
            badge.setPixmap(qta.icon(icon, color='#2563EB').pixmap(18, 18))
            heading.addWidget(badge)
            value = QLabel('—')
            value.setStyleSheet(ds.METRIC_QSS)
            card.layout().addLayout(heading)
            card.layout().addWidget(value)
            self.metrics.append((caption, value))
            row.addWidget(card, 1)
        self._set_metrics(('Produtos no resultado', 'Unidades em estoque', 'Produtos ativos'))
        return row

    def _set_metrics(self, captions, values=None):
        for index, (caption, value) in enumerate(self.metrics):
            caption.setText(captions[index])
            value.setText(str(values[index]) if values is not None else '—')

    def _filters(self):
        card = _card('reportFilters')
        card.layout().setContentsMargins(18, 14, 18, 14)
        row = QHBoxLayout()
        self.kind = _combo(['Estoque', 'Vendas'])
        self.search = _line_edit('Buscar código, produto ou categoria…')
        self.search.setClearButtonEnabled(True)
        self.status = _combo(['Todos', 'Ativos', 'Inativos'])
        for label, widget, stretch in (
            ('Tipo de relatório', self.kind, 1),
            ('Buscar no relatório', self.search, 2),
            ('Situação do produto', self.status, 1),
        ):
            field = _field(label)
            field.layout().addWidget(widget)
            widget.setAccessibleName(label)
            row.addWidget(field, stretch)
            if widget is self.status:
                self.status_field = field
        card.layout().addLayout(row)
        return card

    def _results(self):
        card = _card('reportResults')
        card.layout().setContentsMargins(18, 16, 18, 14)
        heading = QHBoxLayout()
        self.result_title = QLabel('Posição de estoque')
        self.result_title.setStyleSheet(ds.SECTION_TITLE_QSS)
        self.updated_at = QLabel('Aguardando atualização')
        self.updated_at.setStyleSheet('color: #64748B; font-size: 12px;')
        heading.addWidget(self.result_title, 1)
        heading.addWidget(self.updated_at)
        card.layout().addLayout(heading)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(inventory.TABLE_QSS)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.horizontalHeader().setMinimumSectionSize(80)
        self.table.setMinimumHeight(140)
        card.layout().addWidget(self.table, 1)
        self.empty = QLabel('Atualize para consultar os dados da empresa.')
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet(inventory.LIST_STATE_QSS)
        card.layout().addWidget(self.empty)
        self.result_count = QLabel('0 registros')
        self.result_count.setStyleSheet('color: #64748B; font-size: 12px;')
        card.layout().addWidget(self.result_count)
        return card

    def refresh(self):
        stock = self.kind.currentIndex() == 0
        self.status_field.setVisible(stock)
        self.search.setPlaceholderText('Buscar código, produto ou categoria…' if stock else 'Buscar venda, cliente ou produto…')
        self.result_title.setText('Posição de estoque' if stock else 'Vendas registradas')
        self.headers = (['Código', 'Produto', 'Categoria', 'Saldo', 'Mínimo', 'Ativo'] if stock
                        else ['Venda', 'Cliente', 'Produto', 'Valor', 'Data', 'Status'])
        self._set_metrics(('Produtos no resultado', 'Unidades em estoque', 'Produtos ativos') if stock
                          else ('Vendas no resultado', 'Valor total', 'Valor médio por venda'))
        self.error.hide()
        self._loaded = False
        self._all_rows = []
        self._apply_filters()
        self.updated_at.setText('Carregando…')
        self.refresh_button.setEnabled(False)

        def fetch():
            if stock:
                rows = [(p.code, p.name, p.category, p.stock,
                         '' if p.minimum_stock is None else p.minimum_stock, 'Sim' if p.active else 'Não')
                        for p in self.read_products()]
            else:
                rows = [(s['id'], s['cliente'], s['produto'], s['total'], s['data'],
                         SaleStatus.from_value(s.get('status') or 'CONCLUIDA').label)
                        for s in self.sales.list_all()]
            return rows

        self.loader.load(fetch, self._loaded_rows, self._load_failed)

    def _loaded_rows(self, rows):
        self._all_rows = rows
        self._loaded = True
        self._apply_filters()
        self.updated_at.setText('Atualizado às ' + datetime.now().strftime('%H:%M'))
        self.refresh_button.setEnabled(True)

    def _load_failed(self, error):
        self._loaded = False
        self._all_rows = []
        self._apply_filters()
        for _, value in self.metrics:
            value.setText('—')
        self.updated_at.setText('Atualização não concluída')
        self.empty.setText('Não foi possível carregar o relatório. Tente atualizar novamente.')
        self.error.setStyleSheet(inventory.LOAD_ERROR_QSS)
        self.error.setText(f'Não foi possível atualizar: {error}')
        self.error.show()

        self.refresh_button.setEnabled(True)

    def _apply_filters(self):
        query = self.search.text().strip().casefold()
        stock = self.kind.currentIndex() == 0
        status = self.status.currentIndex() if stock else 0
        self.rows = [row for row in self._all_rows
                     if (not query or query in ' '.join(map(str, row[:3])).casefold())
                     and (not status or row[5] == ('Sim' if status == 1 else 'Não'))]
        if self._loaded:
            if stock:
                values = (len(self.rows), sum(int(row[3]) for row in self.rows), sum(row[5] == 'Sim' for row in self.rows))
            else:
                # Linha revertida continua LISTADA — o histórico aconteceu —
                # mas fica fora do dinheiro, senão o relatório soma receita
                # que foi desfeita (US17).
                valem = [row for row in self.rows
                         if row[5] not in (SaleStatus.CANCELADA.label,
                                           SaleStatus.DEVOLVIDA.label)]
                total = sum((Decimal(str(row[3])) for row in valem), Decimal(0))
                values = (len(self.rows), money(total),
                          money(total / len(valem) if valem else Decimal(0)))
            for (_, label), value in zip(self.metrics, values):
                label.setText(str(value))
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setRowCount(len(self.rows))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        if self.headers:
            header.setSectionResizeMode(1 if stock else 2, QHeaderView.Stretch)
        for i, row in enumerate(self.rows):
            for j, value in enumerate(row):
                text = money(Decimal(str(value))) if not stock and j == 3 else str(value)
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if j in ((3, 4) if stock else (3,)):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if stock and j == 5:
                    item.setForeground(QColor('#15803D' if value == 'Sim' else '#64748B'))
                self.table.setItem(i, j, item)
        if self._loaded:
            self.empty.setText('Nenhum resultado para os filtros aplicados.' if self._all_rows else 'Nenhum registro disponível neste relatório.')
        self.empty.setVisible(not self.rows)
        self.table.setVisible(bool(self.rows))
        self.result_count.setText(f'{len(self.rows)} de {len(self._all_rows)} registros · Indicadores e CSV seguem os filtros aplicados')
        self.export_button.setEnabled(self._loaded and bool(self.rows))

    def export_csv(self, path):
        def safe(value):
            text = str(value)
            return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text
        with open(path, 'w', encoding='utf-8-sig', newline='') as output:
            writer = csv.writer(output, delimiter=';')
            writer.writerow(self.headers)
            writer.writerows([safe(value) for value in row] for row in self.rows)

    def _choose_export(self):
        filename = f'relatorio_{self.kind.currentText().lower()}_{datetime.now():%Y-%m-%d}.csv'
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar relatório', filename, 'CSV (*.csv)')
        if path:
            try:
                self.export_csv(path)
                self.error.setStyleSheet('color: #15803D; font-size: 13px;')
                self.error.setText('Relatório exportado com os filtros aplicados.')
            except OSError as error:
                self.error.setStyleSheet(inventory.LOAD_ERROR_QSS)
                self.error.setText(f'Não foi possível exportar: {error}')
            self.error.show()
