"""Indicadores de vendas e estoque por período (US16).

Irmã do Dashboard, e separada dele de propósito: a "Visão geral" é de todos
os papéis e responde "o que precisa de reposição agora"; esta tela é de
gestão, responde "quanto vendemos no período" e por isso tem alçada própria
na matriz (`indicadores`, só ADMIN).

Nenhuma regra de negócio mora aqui. O recorte das vendas é do
`IndicatorsService`, o cálculo é de `domain/sales_indicators.py`, e a
permissão é conferida no serviço — esconder o menu é controle visual, e
controle visual se burla.
"""

from datetime import date

import qtawesome as qta
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDateEdit, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from stockflow.presentation.pages.reports import money
from stockflow.presentation.styles import design_system as ds
from stockflow.presentation.styles import inventory
from stockflow.presentation.widgets.form_fields import _card, _card_header, _field
from stockflow.presentation.workers import PageLoader

#: Cor do rótulo de situação, igual à da tabela de reposição do Dashboard.
#: Repetir o vermelho/âmbar aqui mantém "Crítico" com a mesma leitura nas
#: duas telas; inventar uma terceira paleta faria o mesmo estado parecer
#: dois problemas diferentes.
COR_DA_SITUACAO = {"Crítico": "#B91C1C", "Baixo": "#B45309"}


class IndicadoresPage(QWidget):
    def __init__(self, service, session=None):
        super().__init__()
        self.loader = PageLoader(self)
        self._service = service
        self.session = session
        self.setObjectName("indicadoresPage")
        self.setStyleSheet(ds.page_qss("indicadoresPage") + ds.field_qss())
        layout = QVBoxLayout(self)
        ds.page_layout(layout)
        layout.addLayout(self._header())
        layout.addWidget(self._filters())
        layout.addLayout(self._metrics())
        layout.addWidget(self._ranking(), 1)
        layout.addWidget(self._low_stock(), 1)
        self.error = QLabel()
        self.error.setTextFormat(Qt.PlainText)
        self.error.setWordWrap(True)
        self.error.setStyleSheet(inventory.LOAD_ERROR_QSS)
        self.error.hide()
        layout.addWidget(self.error)
        self.summary = QLabel("Aguardando atualização")
        self.summary.setTextFormat(Qt.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("color: #64748B; font-size: 12px;")
        layout.addWidget(self.summary)

    # ------------------------------------------------------------ montagem

    def _header(self):
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(4)
        title = QLabel("Indicadores")
        title.setStyleSheet(inventory.TITLE_QSS)
        subtitle = QLabel(
            "Acompanhe o desempenho comercial do período e os produtos que "
            "precisam de reposição."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(inventory.SUBTITLE_QSS)
        text.addWidget(title)
        text.addWidget(subtitle)
        row.addLayout(text, 1)
        self.refresh_button = QPushButton("Atualizar")
        self.refresh_button.setIcon(qta.icon("fa5s.sync-alt", color="#475569"))
        self.refresh_button.setStyleSheet(inventory.FILTER_QSS)
        self.refresh_button.setFixedHeight(ds.CONTROL_HEIGHT)
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        return row

    def _filters(self):
        card = _card("indicadoresFilters")
        card.layout().setContentsMargins(18, 14, 18, 14)
        row = QHBoxLayout()
        # Mês corrente: é o recorte que alguém quer ver ao abrir a tela, e
        # nasce VÁLIDO — um período vazio exigiria escolher duas datas antes
        # de a tela dizer qualquer coisa.
        hoje = date.today()
        self.date_start = self._date_edit(
            "Data inicial dos indicadores", hoje.replace(day=1)
        )
        self.date_end = self._date_edit("Data final dos indicadores", hoje)
        for rotulo, widget in (("De", self.date_start), ("Até", self.date_end)):
            field = _field(rotulo)
            field.layout().addWidget(widget)
            row.addWidget(field, 1)
        self.apply_button = QPushButton("Aplicar período")
        self.apply_button.setIcon(qta.icon("fa5s.filter", color="white"))
        self.apply_button.setStyleSheet(inventory.NEW_BUTTON_QSS)
        self.apply_button.setFixedHeight(ds.CONTROL_HEIGHT)
        self.apply_button.setCursor(Qt.PointingHandCursor)
        self.apply_button.clicked.connect(self.refresh)
        row.addWidget(self.apply_button)
        row.addStretch(1)
        card.layout().addLayout(row)
        return card

    @staticmethod
    def _date_edit(nome, valor):
        campo = QDateEdit(QDate(valor.year, valor.month, valor.day))
        campo.setCalendarPopup(True)
        campo.setDisplayFormat("dd/MM/yyyy")
        campo.setAccessibleName(nome)
        campo.setFixedHeight(ds.CONTROL_HEIGHT)
        return campo

    def _metrics(self):
        row = QHBoxLayout()
        row.setSpacing(14)
        self.metric_values = []
        for indice, (legenda, icone, detalhe) in enumerate((
            ("Faturamento total", "fa5s.dollar-sign",
             "Soma das vendas confirmadas no período"),
            ("Quantidade de vendas", "fa5s.receipt",
             "Cada venda conta uma vez, com um ou vários itens"),
            ("Ticket médio", "fa5s.balance-scale",
             "Faturamento dividido pela quantidade de vendas"),
        )):
            card = _card(f"indicadorMetric{indice}")
            card.layout().setContentsMargins(18, 16, 18, 16)
            card.layout().setSpacing(8)
            topo = QHBoxLayout()
            rotulo = QLabel(legenda)
            rotulo.setWordWrap(True)
            rotulo.setStyleSheet("color: #64748B; font-size: 12px;")
            topo.addWidget(rotulo, 1)
            selo = QLabel()
            selo.setPixmap(qta.icon(icone, color="#2563EB").pixmap(18, 18))
            topo.addWidget(selo)
            valor = QLabel("—")
            valor.setStyleSheet(ds.METRIC_QSS)
            nota = QLabel(detalhe)
            nota.setWordWrap(True)
            nota.setStyleSheet("color: #64748B; font-size: 12px;")
            card.layout().addLayout(topo)
            card.layout().addWidget(valor)
            card.layout().addWidget(nota)
            self.metric_values.append(valor)
            row.addWidget(card, 1)
        return row

    def _ranking(self):
        card = _card("indicadoresRanking")
        card.layout().addLayout(_card_header(
            "fa5s.trophy", "Produtos mais vendidos",
            "Quantidade comercializada no período, da maior para a menor.",
        ))
        self.ranking_table = self._table(["Produto", "Código", "Quantidade vendida"])
        card.layout().addWidget(self.ranking_table, 1)
        self.ranking_empty = QLabel("Atualize para consultar os produtos vendidos.")
        self.ranking_empty.setAlignment(Qt.AlignCenter)
        self.ranking_empty.setWordWrap(True)
        self.ranking_empty.setStyleSheet(inventory.LIST_STATE_QSS)
        card.layout().addWidget(self.ranking_empty)
        return card

    def _low_stock(self):
        card = _card("indicadoresLowStock")
        card.layout().addLayout(_card_header(
            "fa5s.exclamation-triangle", "Produtos abaixo do estoque mínimo",
            "Situação atual do estoque, independente do período consultado.",
        ))
        self.low_stock_table = self._table(
            ["Código", "Produto", "Saldo atual", "Estoque mínimo", "Situação"]
        )
        card.layout().addWidget(self.low_stock_table, 1)
        self.low_stock_empty = QLabel("Atualize para consultar o estoque.")
        self.low_stock_empty.setAlignment(Qt.AlignCenter)
        self.low_stock_empty.setWordWrap(True)
        self.low_stock_empty.setStyleSheet(inventory.LIST_STATE_QSS)
        card.layout().addWidget(self.low_stock_empty)
        return card

    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setStyleSheet(inventory.TABLE_QSS)
        table.setShowGrid(False)
        table.setMinimumHeight(140)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(ds.ROW_HEIGHT)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        # A coluna do nome estica; as demais seguem o conteúdo. Sem isto a
        # tabela reserva largura igual para "Quantidade vendida" e para o
        # nome do produto, e o nome é o que precisa caber.
        header.setSectionResizeMode(headers.index("Produto"), QHeaderView.Stretch)
        return table

    # ------------------------------------------------------------- consulta

    def refresh(self, *_):
        """Consulta os indicadores do período selecionado.

        O período invertido é recusado AQUI, antes de qualquer consulta:
        `SaleFilter` também o recusa, mas deixar a recusa só lá gastaria uma
        ida à rede para dizer o que a tela já sabia.
        """
        inicio = self.date_start.date().toPython()
        fim = self.date_end.date().toPython()
        if inicio > fim:
            self._show_error("A data inicial não pode ser posterior à data final.")
            self.summary.setText("Período inválido")
            return

        self.error.hide()
        self._set_busy(True)
        self.summary.setText("Carregando indicadores…")
        sessao = self.session

        def consultar():
            return (
                self._service.commercial(sessao, inicio, fim),
                self._service.low_stock(sessao),
            )

        self.loader.load(consultar, self._loaded, self._failed)

    def _loaded(self, resultado):
        comercial, baixos = resultado
        self.metric_values[0].setText(money(comercial.revenue))
        self.metric_values[1].setText(str(comercial.sales_count))
        self.metric_values[2].setText(money(comercial.average_ticket))
        self._fill(
            self.ranking_table, self.ranking_empty,
            [(item.name, item.code, str(item.quantity)) for item in comercial.ranking],
            "Nenhuma venda confirmada no período selecionado.",
            numericas=(2,),
        )
        self._fill(
            self.low_stock_table, self.low_stock_empty,
            [(item.code, item.name, str(item.stock), str(item.minimum), item.status)
             for item in baixos],
            "Nenhum produto abaixo do estoque mínimo configurado.",
            numericas=(2, 3), situacao=4,
        )
        self.summary.setText(
            f"Período de {self.date_start.text()} a {self.date_end.text()} · "
            "estoque baixo reflete o saldo atual"
        )
        self._set_busy(False)

    def _failed(self, erro):
        """Consulta que falhou apaga os números em vez de mantê-los.

        Deixar o valor da consulta anterior na tela com uma mensagem de erro
        embaixo é pior do que não mostrar nada: o número continua parecendo
        atual, e é por ele que alguém decide uma compra.
        """
        for valor in self.metric_values:
            valor.setText("—")
        for tabela in (self.ranking_table, self.low_stock_table):
            tabela.setRowCount(0)
            tabela.hide()
        self.ranking_empty.setText("Não foi possível consultar os indicadores.")
        self.ranking_empty.show()
        self.low_stock_empty.setText("Não foi possível consultar o estoque.")
        self.low_stock_empty.show()
        self._show_error(f"Não foi possível atualizar: {erro}")
        self.summary.setText("Atualização não concluída")
        self._set_busy(False)

    def _show_error(self, mensagem):
        self.error.setText(mensagem)
        self.error.show()

    def _set_busy(self, carregando):
        for botao in (self.refresh_button, self.apply_button):
            botao.setEnabled(not carregando)

    @staticmethod
    def _fill(tabela, vazio, linhas, mensagem, numericas=(), situacao=None):
        tabela.setRowCount(len(linhas))
        for i, linha in enumerate(linhas):
            for j, valor in enumerate(linha):
                item = QTableWidgetItem(valor)
                item.setToolTip(valor)
                if j in numericas:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == situacao and valor in COR_DA_SITUACAO:
                    item.setForeground(QColor(COR_DA_SITUACAO[valor]))
                tabela.setItem(i, j, item)
        vazio.setText(mensagem)
        vazio.setVisible(not linhas)
        tabela.setVisible(bool(linhas))
