"""Consulta e exportação dos relatórios da empresa atual."""

from stockflow.presentation.styles import design_system as ds

from datetime import date, datetime
from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QDateEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from stockflow.application.dto.sale_filter import (
    TAMANHO_MAXIMO,
    SaleFilter,
)
from stockflow.application.services.csv_exporter import export_csv
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.permissions import exigir_ver, pode_ver
from stockflow.infrastructure.repositories.product_mapper import money_to_label
from stockflow.presentation.workers import PageLoader
from stockflow.presentation.styles import inventory
from stockflow.presentation.widgets.form_fields import _card, _combo, _field, _line_edit


_RELATORIOS = (
    ("estoque", "Estoque", "estoque"),
    ("vendas", "Vendas", "vendas"),
    ("movimentacoes", "Movimentações", "movimentacoes"),
    ("auditoria", "Auditoria", "historico_precos"),
)


def money(value):
    return 'R$ ' + f'{value:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


class ReportsPage(QWidget):
    def __init__(
        self, products, sales, session=None, *, sale_service=None,
        movement_service=None, price_history_service=None,
    ):
        super().__init__()
        self.loader = PageLoader(self)
        self.read_products = products.list_all
        self.products, self.sales = products, sales
        self.session = session
        self.sale_service = sale_service
        self.movement_service = movement_service
        self.price_history_service = price_history_service
        self.rows, self.headers, self._all_rows = [], [], []
        self._sale_filters = {}
        self._loaded = False
        self._configured_kind = None
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
        self.product_filter.currentIndexChanged.connect(self._apply_filters)
        self.movement_kind_filter.currentIndexChanged.connect(self._apply_filters)
        self.client_filter.currentIndexChanged.connect(self._apply_filters)
        self.seller_filter.currentIndexChanged.connect(self._apply_filters)
        self.period_filter.toggled.connect(self._period_changed)
        self.date_start.dateChanged.connect(self._apply_filters)
        self.date_end.dateChanged.connect(self._apply_filters)

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
        rows = QVBoxLayout()

        first_row = QHBoxLayout()
        self.kind = QComboBox()
        for key, label, area in _RELATORIOS:
            if pode_ver(self.session, area):
                self.kind.addItem(label, key)
        if not self.kind.count():
            self.kind.addItem('Nenhum relatório autorizado', None)
            self.kind.setEnabled(False)
        self.search = _line_edit('Buscar código, produto ou categoria…')
        self.search.setClearButtonEnabled(True)
        for label, widget, stretch in (
            ('Tipo de relatório', self.kind, 1),
            ('Buscar no relatório', self.search, 2),
        ):
            field = _field(label)
            field.layout().addWidget(widget)
            widget.setAccessibleName(label)
            first_row.addWidget(field, stretch)
        rows.addLayout(first_row)

        filters_row = QHBoxLayout()
        self.status = _combo([])
        self.product_filter = _combo(['Todos os produtos'])
        self.movement_kind_filter = _combo(['Todos os tipos'])
        self.client_filter = _combo(['Todos os clientes'])
        self.seller_filter = _combo(['Todos os vendedores'])
        self.status_field = self._add_filter(filters_row, 'Situação', self.status)
        self.product_field = self._add_filter(filters_row, 'Produto', self.product_filter)
        self.kind_field = self._add_filter(filters_row, 'Espécie', self.movement_kind_filter)
        self.client_field = self._add_filter(filters_row, 'Cliente', self.client_filter)
        self.seller_field = self._add_filter(filters_row, 'Vendedor', self.seller_filter)
        rows.addLayout(filters_row)

        period_row = QHBoxLayout()
        self.period_filter = QCheckBox('Filtrar período')
        self.period_filter.setAccessibleName('Aplicar filtro de período')
        self.period_field = _field('Período')
        self.period_field.layout().addWidget(self.period_filter)
        period_row.addWidget(self.period_field)
        self.date_start = QDateEdit(QDate.currentDate())
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat('dd/MM/yyyy')
        self.date_start.setAccessibleName('Data inicial do relatório')
        self.date_end = QDateEdit(QDate.currentDate())
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat('dd/MM/yyyy')
        self.date_end.setAccessibleName('Data final do relatório')
        self.date_start_field = self._add_filter(period_row, 'De', self.date_start)
        self.date_end_field = self._add_filter(period_row, 'Até', self.date_end)
        self.date_start.setEnabled(False)
        self.date_end.setEnabled(False)
        period_row.addStretch(1)
        rows.addLayout(period_row)
        card.layout().addLayout(rows)
        return card

    @staticmethod
    def _add_filter(row, label, widget):
        field = _field(label)
        field.layout().addWidget(widget)
        row.addWidget(field, 1)
        return field

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

    def _period_changed(self, checked):
        self.date_start.setEnabled(checked)
        self.date_end.setEnabled(checked)
        self._apply_filters()

    def _configure_status(self, kind):
        options = {
            'estoque': [('Todos', None), ('Ativos', True), ('Inativos', False)],
            'vendas': [('Todas as situações', None)] + [
                (status.label, status.value) for status in SaleStatus
            ],
            'movimentacoes': [('Todas as situações', None)] + [
                ('Confirmada', 'Confirmada'),
                ('Pendente', 'Pendente'),
                ('Cancelada', 'Cancelada'),
            ],
            'auditoria': [('Todas as situações', None)],
        }[kind]
        self.status.blockSignals(True)
        self.status.clear()
        for label, value in options:
            self.status.addItem(label, value)
        self.status.blockSignals(False)

    def _configure_visibility(self, kind):
        stock = kind == 'estoque'
        sales = kind == 'vendas'
        movements = kind == 'movimentacoes'
        audit = kind == 'auditoria'
        self.search.setPlaceholderText(
            'Buscar código, produto ou categoria…' if stock else
            'Buscar venda, cliente ou produto…' if sales else
            'Buscar produto, fornecedor ou observação…' if movements else
            'Buscar produto, campo ou responsável…'
        )
        self.status_field.setVisible(stock or sales or movements)
        self.product_field.setVisible(movements or audit)
        self.kind_field.setVisible(movements)
        self.client_field.setVisible(sales)
        self.seller_field.setVisible(sales)
        self.period_field.setVisible(sales or movements)
        self.date_start_field.setVisible(sales or movements)
        self.date_end_field.setVisible(sales or movements)

    def refresh(self, *_):
        kind = self.kind.currentData()
        if kind is None:
            self._loaded = False
            self._all_rows = []
            self._apply_filters()
            self.updated_at.setText('Nenhum relatório disponível')
            return
        if kind != self._configured_kind:
            self._loaded = False
            self._all_rows = []
            self.rows = []
            self._configured_kind = kind
            self._configure_status(kind)
            self.product_filter.setCurrentIndex(0)
            self.movement_kind_filter.setCurrentIndex(0)
            self.client_filter.setCurrentIndex(0)
            self.seller_filter.setCurrentIndex(0)
            self.period_filter.setChecked(False)
            self.search.clear()
        self._configure_visibility(kind)
        labels = {
            'estoque': ('Posição de estoque',
                        ['Código', 'Produto', 'Categoria', 'Saldo', 'Mínimo', 'Ativo'],
                        ('Produtos no resultado', 'Unidades em estoque', 'Produtos ativos')),
            'vendas': ('Vendas registradas',
                       ['Venda', 'Cliente', 'Produto', 'Valor', 'Data', 'Status', 'Vendedor'],
                       ('Vendas no resultado', 'Valor total', 'Valor médio por venda')),
            'movimentacoes': ('Movimentações de estoque',
                              ['Movimentação', 'Código', 'Produto', 'Espécie', 'Quantidade',
                               'Situação', 'Observação', 'Quando', 'Fornecedor', 'Motivo'],
                              ('Movimentações no resultado', 'Unidades de entrada confirmadas',
                               'Unidades de saída confirmadas')),
            'auditoria': ('Auditoria de preços e custos',
                          ['Quando', 'Produto', 'Campo', 'De', 'Para', 'Por'],
                          ('Alterações no resultado', 'Produtos afetados', 'Campos alterados')),
        }
        self.result_title.setText(labels[kind][0])
        self.headers = labels[kind][1]
        self._set_metrics(labels[kind][2])
        self.error.hide()
        self._loaded = False
        self._all_rows = []
        self._apply_filters()
        self.updated_at.setText('Carregando…')
        self.refresh_button.setEnabled(False)

        def fetch():
            exigir_ver(self.session, dict((key, area) for key, _, area in _RELATORIOS)[kind],
                       f'consultar relatório de {kind}')
            if kind == 'estoque':
                return [
                    (p.code, p.name, p.category, p.stock,
                     '' if p.minimum_stock is None else p.minimum_stock,
                     'Sim' if p.active else 'Não')
                    for p in self.read_products()
                ]
            if kind == 'vendas':
                return self._load_sales()
            if kind == 'movimentacoes':
                if self.movement_service is None:
                    raise RuntimeError('O serviço de movimentações não foi configurado.')
                return [tuple(mov) for mov in self.movement_service.list_movements(self.session)]
            if self.price_history_service is None:
                raise RuntimeError('O serviço de auditoria não foi configurado.')
            return [self._audit_row(change) for change in
                    self.price_history_service.list_changes(self.session)]

        self.loader.load(fetch, self._loaded_rows, self._load_failed)

    def _load_sales(self):
        self._sale_filters = {}
        if self.sale_service is None:
            rows = self.sales.list_all()
        else:
            rows = []
            for filtro in (SaleFilter(), SaleFilter(status=SaleStatus.PENDENTE.value)):
                page_number = 1
                while True:
                    page = self.sale_service.list_sales(
                        self.session, filtro, page_number, TAMANHO_MAXIMO
                    )
                    rows.extend(page.rows)
                    if page_number >= page.pages or not page.rows:
                        break
                    page_number += 1
        mapped = []
        for sale in rows:
            status = sale.get('status') or SaleStatus.CONCLUIDA.value
            sale_id = str(sale.get('id', ''))
            self._sale_filters[sale_id] = (
                sale.get('client_id') or sale.get('cliente', ''),
                sale.get('seller_id') or sale.get('seller', ''),
            )
            mapped.append((
                sale_id,
                sale.get('cliente', ''),
                sale.get('produto', ''),
                sale.get('total', 0),
                sale.get('data', ''),
                SaleStatus.from_value(status).label,
                sale.get('seller', ''),
            ))
        mapped.sort(key=lambda row: _row_date(row[4]) or date.min, reverse=True)
        return mapped

    @staticmethod
    def _audit_row(change):
        when = (
            change.changed_on.astimezone().strftime('%d/%m/%Y %H:%M')
            if change.changed_on else '—'
        )
        product = f'{change.product_code} — {change.product_name}'.strip(' —')
        field = getattr(change.field, 'label', str(change.field))
        old_value = '—' if change.old_price is None else money_to_label(change.old_price)
        new_value = '—' if change.new_price is None else money_to_label(change.new_price)
        return (when, product, field, old_value, new_value, change.changed_by or '—')

    def _loaded_rows(self, rows):
        self._all_rows = rows
        self._populate_filter_options()
        self._loaded = True
        self._apply_filters()
        self.updated_at.setText('Atualizado às ' + datetime.now().strftime('%H:%M'))
        self.refresh_button.setEnabled(True)

    def _populate_filter_options(self):
        kind = self.kind.currentData()
        if kind in ('movimentacoes', 'auditoria'):
            if kind == 'movimentacoes':
                choices = {
                    row[1]: f'{row[1]} — {row[2]}'.strip(' —')
                    for row in self._all_rows if len(row) > 2 and row[1] and row[1] != '—'
                }
            else:
                choices = {
                    row[1].split(' — ', 1)[0]: row[1] for row in self._all_rows
                    if len(row) > 1 and row[1] and row[1] != '—'
                }
            self._replace_options(self.product_filter, 'Todos os produtos', choices.items())
        if kind == 'movimentacoes':
            self._replace_options(
                self.movement_kind_filter, 'Todos os tipos',
                ((kind.value, kind.label) for kind in MovementKind),
            )
        if kind == 'vendas':
            clientes = {}
            vendedores = {}
            for row in self._all_rows:
                client_id, seller_id = self._sale_filters.get(row[0], (row[1], row[6]))
                if client_id:
                    clientes.setdefault(client_id, str(row[1] or client_id))
                if seller_id and seller_id != '—':
                    vendedores.setdefault(seller_id, str(row[6] or seller_id))
            self._replace_options(self.client_filter, 'Todos os clientes', clientes.items())
            self._replace_options(self.seller_filter, 'Todos os vendedores', vendedores.items())

    @staticmethod
    def _replace_options(combo, placeholder, options):
        selected = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
        for value, label in options:
            combo.addItem(str(label), value)
        index = combo.findData(selected) if selected is not None else 0
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

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

    def _apply_filters(self, *_):
        query = self.search.text().strip().casefold()
        kind = self.kind.currentData()
        status = self.status.currentData()
        product_code = self.product_filter.currentData()
        movement_kind = self.movement_kind_filter.currentData()
        client_id = self.client_filter.currentData()
        seller_id = self.seller_filter.currentData()
        start = self.date_start.date().toPython()
        end = self.date_end.date().toPython()
        invalid_period = self.period_filter.isChecked() and start > end

        self.rows = []
        for row in self._all_rows:
            searchable = (
                row[:3] if kind in ('estoque', 'vendas') else
                row[1:] if kind == 'movimentacoes' else row[1:6]
            )
            if query and query not in ' '.join(map(str, searchable)).casefold():
                continue
            if status is not None:
                if kind == 'estoque' and (row[5] == 'Sim') != status:
                    continue
                if kind == 'vendas' and row[5] != SaleStatus.from_value(status).label:
                    continue
                if kind == 'movimentacoes' and row[5] != status:
                    continue
            if product_code is not None:
                if kind == 'movimentacoes' and row[1] != product_code:
                    continue
                if kind == 'auditoria' and not row[1].startswith(f'{product_code} —'):
                    continue
            if movement_kind is not None and row[3] != MovementKind.from_value(movement_kind).label:
                continue
            if kind == 'vendas':
                sale_client, sale_seller = self._sale_filters.get(row[0], (row[1], row[6]))
                if client_id is not None and sale_client != client_id:
                    continue
                if seller_id is not None and sale_seller != seller_id:
                    continue
            if self.period_filter.isChecked():
                row_date = _row_date(row[4]) if kind == 'vendas' else _row_date(row[7])
                if invalid_period or row_date is None or not start <= row_date <= end:
                    continue
            self.rows.append(row)

        if self._loaded:
            if kind == 'estoque':
                values = (
                    len(self.rows),
                    sum(int(row[3]) for row in self.rows),
                    sum(row[5] == 'Sim' for row in self.rows),
                )
            elif kind == 'vendas':
                valid_sales = [
                    row for row in self.rows
                    if row[5] not in (
                        SaleStatus.CANCELADA.label, SaleStatus.DEVOLVIDA.label,
                        SaleStatus.PENDENTE.label,
                    )
                ]
                total = sum((Decimal(str(row[3])) for row in valid_sales), Decimal(0))
                values = (
                    len(self.rows), money(total),
                    money(total / len(valid_sales) if valid_sales else Decimal(0)),
                )
            elif kind == 'movimentacoes':
                confirmed = [row for row in self.rows if row[5] == 'Confirmada']
                entries = sum(int(row[4]) for row in confirmed if row[3] == 'Entrada')
                exits = sum(int(row[4]) for row in confirmed if row[3] == 'Saída')
                values = (len(self.rows), entries, exits)
            else:
                values = (
                    len(self.rows),
                    len({row[1].split(' — ', 1)[0] for row in self.rows if row[1]}),
                    len({row[2] for row in self.rows}),
                )
            for (_, label), value in zip(self.metrics, values):
                label.setText(str(value))

        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setRowCount(len(self.rows))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        if self.headers:
            stretch_column = 1 if kind == 'estoque' else 2 if kind == 'vendas' else 2
            header.setSectionResizeMode(stretch_column, QHeaderView.Stretch)
        for i, row in enumerate(self.rows):
            for j, value in enumerate(row[:len(self.headers)]):
                text = money(Decimal(str(value))) if kind == 'vendas' and j == 3 else str(value)
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if (kind == 'estoque' and j in (3, 4)
                        or kind == 'vendas' and j == 3
                        or kind == 'movimentacoes' and j == 4):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if kind == 'estoque' and j == 5:
                    item.setForeground(QColor('#15803D' if value == 'Sim' else '#64748B'))
                self.table.setItem(i, j, item)
        if self._loaded:
            self.empty.setText(
                'Nenhum resultado para os filtros aplicados.'
                if self._all_rows else 'Nenhum registro disponível neste relatório.'
            )
        self.empty.setVisible(not self.rows)
        self.table.setVisible(bool(self.rows))
        self.result_count.setText(
            f'{len(self.rows)} de {len(self._all_rows)} registros · '
            'Indicadores e CSV seguem os filtros aplicados'
        )
        self.export_button.setEnabled(self._loaded and bool(self.rows) and kind is not None)
        if invalid_period:
            self.error.setStyleSheet(inventory.LOAD_ERROR_QSS)
            self.error.setText('A data inicial não pode ser posterior à data final.')
            self.error.show()
        elif self.error.isVisible() and self._loaded:
            self.error.hide()

    def export_csv(self, path):
        kind = self.kind.currentData()
        if kind is None:
            raise PermissionDeniedError('Nenhum relatório autorizado para exportação.')
        area = next(area for key, _, area in _RELATORIOS if key == kind)
        exigir_ver(self.session, area, f'exportar relatório de {kind}')
        export_csv(path, self.headers, [row[:len(self.headers)] for row in self.rows])

    def _choose_export(self):
        filename = f'relatorio_{self.kind.currentText().lower()}_{datetime.now():%Y-%m-%d}.csv'
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar relatório', filename, 'CSV (*.csv)')
        if path:
            try:
                self.export_csv(path)
                self.error.setStyleSheet('color: #15803D; font-size: 13px;')
                self.error.setText('Relatório exportado com os filtros aplicados.')
            except (OSError, PermissionDeniedError) as error:
                self.error.setStyleSheet(inventory.LOAD_ERROR_QSS)
                self.error.setText(f'Não foi possível exportar: {error}')
            self.error.show()


def _row_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or '').strip()
    if not text or text == '—':
        return None
    if text.casefold().startswith('hoje'):
        return date.today()
    if text.casefold().startswith('ontem'):
        from datetime import timedelta
        return date.today() - timedelta(days=1)
    for pattern in ('%d/%m/%Y %H:%M', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(text[:19], pattern).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).date()
    except ValueError:
        return None
