"""Consulta e detalhes somente leitura da auditoria de preços e custos."""

from stockflow.presentation.styles import design_system as ds

from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QPushButton, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from stockflow.infrastructure.repositories.product_mapper import money_to_label
from stockflow.presentation.styles import inventory

from stockflow.domain.enums.price_edit_field import PriceEditField
from stockflow.domain.permissions import pode_ver
from stockflow.presentation.dialogs.audit_event_dialog import AuditEventDialog

COLUNAS = ("Quando", "Produto", "Campo", "De", "Para", "Por")

#: Valor ausente. "antes não havia custo" não é "o custo era zero", e a tela
#: é o último lugar onde essa distinção pode ser perdida.
AUSENTE = "—"


class HistoricoPrecosPage(QWidget):

    filtro_alterado = Signal(object)

    def __init__(self):
        super().__init__()
        self.session = None
        self._mudancas = ()
        self._visiveis = ()
        self.detail_dialog = None
        self.setObjectName("historicoPrecosPage")
        self.setStyleSheet(ds.page_qss("historicoPrecosPage") + ds.field_qss() + ds.surface_qss("QFrame#historyFilter, QFrame#historyTableCard"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN)
        layout.setSpacing(ds.SECTION_GAP)

        titulo = QLabel("Histórico de preços")
        titulo.setObjectName("pageTitle")
        subtitulo = QLabel(
            "Alterações de preço de venda e de custo, da mais recente para a mais antiga."
        )
        subtitulo.setObjectName("pageSubtitle")
        subtitulo.setWordWrap(True)

        self.produto_combo = QComboBox()
        self.produto_combo.setFixedHeight(ds.CONTROL_HEIGHT)
        self.produto_combo.setMinimumContentsLength(18)
        self.produto_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.produto_combo.setAccessibleName("Produto do histórico")
        self.produto_combo.addItem("Todos os produtos", None)
        self.produto_combo.currentIndexChanged.connect(self._emitir_filtro)

        self.filter_card = QFrame()
        self.filter_card.setObjectName("historyFilter")
        filtros = QVBoxLayout(self.filter_card)
        filtro = QHBoxLayout()
        filtros.addLayout(filtro)
        filtro.setContentsMargins(16, 12, 16, 12)
        filtro.setSpacing(12)
        filtro_label = QLabel("Filtrar por produto")
        filtro_label.setStyleSheet("font-weight: 600; color: #475569;")
        filtro.addWidget(filtro_label)
        filtro.addWidget(self.produto_combo, 1)

        self.usuario_combo = QComboBox()
        self.usuario_combo.addItem("Todos os usuários", None)
        self.acao_combo = QComboBox()
        self.acao_combo.addItem("Todas as ações", None)
        self.acao_combo.addItem("Alteração de preço de venda", PriceEditField.SELL_PRICE)
        self.acao_combo.addItem("Alteração de custo", PriceEditField.BUY_PRICE)
        self.entidade_combo = QComboBox()
        self.entidade_combo.addItem("Todas as entidades", None)
        self.entidade_combo.addItem("Produto", "produto")
        row = QHBoxLayout()
        for title, combo in (("Usuário", self.usuario_combo), ("Ação", self.acao_combo),
                             ("Entidade", self.entidade_combo)):
            field = QVBoxLayout()
            field.addWidget(QLabel(title))
            field.addWidget(combo)
            combo.setAccessibleName(title)
            combo.setFixedHeight(ds.CONTROL_HEIGHT)
            combo.currentIndexChanged.connect(self._aplicar_filtros)
            row.addLayout(field, 1)
        filtros.addLayout(row)
        period = QHBoxLayout()
        self.periodo_check = QCheckBox("Filtrar período")
        period.addWidget(self.periodo_check)
        self.data_inicio = QDateEdit(QDate.currentDate())
        self.data_fim = QDateEdit(QDate.currentDate())
        for title, date in (("De", self.data_inicio), ("Até", self.data_fim)):
            period.addWidget(QLabel(title))
            date.setAccessibleName("Data inicial" if title == "De" else "Data final")
            date.setCalendarPopup(True)
            date.setDisplayFormat("dd/MM/yyyy")
            date.setFixedHeight(ds.CONTROL_HEIGHT)
            date.setEnabled(False)
            date.dateChanged.connect(self._aplicar_filtros)
            period.addWidget(date, 1)
        self.periodo_check.toggled.connect(self._aplicar_filtros)
        clear = QPushButton("Limpar filtros")
        clear.setStyleSheet(inventory.FILTER_QSS)
        clear.setFixedHeight(ds.CONTROL_HEIGHT)
        clear.clicked.connect(self.limpar_filtros)
        period.addWidget(clear)
        filtros.addLayout(period)

        self.table_card = QFrame()
        self.table_card.setObjectName("historyTableCard")
        table_layout = QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(1, 1, 1, 1)
        table_layout.setSpacing(0)

        self.table = QTableWidget(0, len(COLUNAS))
        self.table.setHorizontalHeaderLabels(list(COLUNAS))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setStyleSheet(inventory.TABLE_QSS)
        self.table.setShowGrid(False)
        cabecalho = self.table.horizontalHeader()
        cabecalho.setSectionResizeMode(1, QHeaderView.Stretch)
        for coluna in (0, 2, 3, 4, 5):
            cabecalho.setSectionResizeMode(coluna, QHeaderView.ResizeToContents)
        cabecalho.setMinimumSectionSize(90)
        self.table.verticalHeader().setDefaultSectionSize(ds.ROW_HEIGHT)
        self.table.setAlternatingRowColors(False)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)

        self.empty_label = QLabel("Nenhuma alteração de preço encontrada.")
        self.empty_label.setObjectName("emptyState")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.hide()
        table_layout.addWidget(self.table, 1)
        table_layout.addWidget(self.empty_label)

        self.aviso_label = QLabel("")
        self.aviso_label.setObjectName("warningLabel")
        self.aviso_label.setWordWrap(True)
        self.aviso_label.setTextFormat(Qt.PlainText)
        self.aviso_label.hide()

        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addWidget(self.filter_card)
        layout.addWidget(self.aviso_label)
        layout.addWidget(self.table_card, 1)
        footer = QHBoxLayout()
        self.result_count = QLabel()
        footer.addWidget(self.result_count, 1)
        self.details_button = QPushButton("Ver detalhes do evento")
        self.details_button.setStyleSheet(inventory.NEW_BUTTON_QSS)
        self.details_button.setFixedHeight(ds.CONTROL_HEIGHT)
        self.details_button.setEnabled(False)
        self.details_button.clicked.connect(self.abrir_detalhes)
        self.table.itemSelectionChanged.connect(self._selecao_alterada)
        self.table.cellDoubleClicked.connect(lambda *_: self.abrir_detalhes())
        footer.addWidget(self.details_button)
        layout.addLayout(footer)

    # ------------------------------------------------------------ entrada

    def preencher_produtos(self, produtos) -> None:
        """Alimenta o filtro, preservando a escolha atual quando possível.

        O combo é recarregado junto com o catálogo; sem preservar a escolha,
        editar um produto enquanto o histórico está filtrado jogaria o
        usuário de volta para a lista inteira sem ele ter pedido.
        """
        escolhido = self.produto_combo.currentData()
        self.produto_combo.blockSignals(True)
        self.produto_combo.clear()
        self.produto_combo.addItem("Todos os produtos", None)
        for codigo, nome in produtos:
            self.produto_combo.addItem(f"{codigo} — {nome}", codigo)
        indice = self.produto_combo.findData(escolhido)
        self.produto_combo.setCurrentIndex(max(indice, 0))
        self.produto_combo.blockSignals(False)

    def apply_session(self, session):
        self.session = session
        if self.detail_dialog is not None:
            self.detail_dialog.close()
            self.detail_dialog.deleteLater()
            self.detail_dialog = None
        self._mudancas = ()
        self.usuario_combo.blockSignals(True)
        self.usuario_combo.clear()
        self.usuario_combo.addItem("Todos os usuários", None)
        self.usuario_combo.blockSignals(False)
        self.preencher_produtos(())
        self.limpar_filtros()

    def limpar_filtros(self):
        self.usuario_combo.setCurrentIndex(0)
        self.acao_combo.setCurrentIndex(0)
        self.entidade_combo.setCurrentIndex(0)
        self.periodo_check.setChecked(False)
        self.produto_combo.setCurrentIndex(0)
        self._aplicar_filtros()

    def carregar(self, mudancas) -> None:
        self._mudancas = tuple(mudancas) if pode_ver(self.session, "historico_precos") else ()
        escolhido = self.usuario_combo.currentData()
        self.usuario_combo.blockSignals(True)
        self.usuario_combo.clear()
        self.usuario_combo.addItem("Todos os usuários", None)
        usuarios = {m.changed_by for m in self._mudancas}
        if escolhido is not None and pode_ver(self.session, "historico_precos"):
            usuarios.add(escolhido)
        for user in sorted(usuarios):
            self.usuario_combo.addItem(user or "Não informado", user)
        self.usuario_combo.setCurrentIndex(max(0, self.usuario_combo.findData(escolhido)))
        self.usuario_combo.blockSignals(False)
        self._aplicar_filtros()

    def _aplicar_filtros(self):
        self.aviso_label.hide()
        period = self.periodo_check.isChecked()
        self.data_inicio.setEnabled(period)
        self.data_fim.setEnabled(period)
        start, end = self.data_inicio.date().toPython(), self.data_fim.date().toPython()
        invalid = period and start > end
        user, action = self.usuario_combo.currentData(), self.acao_combo.currentData()
        rows = []
        if not invalid and pode_ver(self.session, "historico_precos"):
            for change in self._mudancas:
                if user is not None and change.changed_by != user:
                    continue
                if action is not None and change.field != action:
                    continue
                if period and (change.changed_on is None or not
                               start <= change.changed_on.astimezone().date() <= end):
                    continue
                rows.append(change)
        # Stable sorting preserves the repository's tie order; undated events go last.
        rows.sort(key=lambda m: m.changed_on.timestamp() if m.changed_on else float('-inf'),
                  reverse=True)
        self._visiveis = tuple(rows)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        self.empty_label.setVisible(not rows and not invalid)
        self.result_count.setText(f"{len(rows)} evento(s) · Mais recentes primeiro")
        for linha, mudanca in enumerate(rows):
            for coluna, texto in enumerate(_celulas(mudanca)):
                item = QTableWidgetItem(texto)
                item.setTextAlignment(
                    Qt.AlignVCenter | (Qt.AlignRight if coluna in (3, 4) else Qt.AlignLeft)
                )
                self.table.setItem(linha, coluna, item)
        if invalid:
            self.aviso_label.setText("A data inicial deve ser anterior ou igual à data final.")
            self.aviso_label.show()
        self._selecao_alterada()

    def _selecao_alterada(self):
        self.details_button.setEnabled(pode_ver(self.session, "historico_precos") and
                                       0 <= self.table.currentRow() < len(self._visiveis))

    def abrir_detalhes(self):
        row = self.table.currentRow()
        if not pode_ver(self.session, "historico_precos") or not 0 <= row < len(self._visiveis):
            return
        if self.detail_dialog is not None:
            self.detail_dialog.close()
            self.detail_dialog.deleteLater()
        self.detail_dialog = AuditEventDialog(self._visiveis[row], self.session, self)
        self.detail_dialog.show()

    def mostrar_recusa(self, erro) -> None:
        """Recusa aparece NA tela, e não num diálogo que some.

        Mesma escolha do card de ajuste: a mensagem fica ao lado do que o
        usuário tentou consultar.
        """
        self.carregar(())
        self.empty_label.hide()
        self.aviso_label.setText(str(erro))
        self.aviso_label.show()

    # ------------------------------------------------------------- saída

    def _emitir_filtro(self) -> None:
        self.filtro_alterado.emit(self.produto_combo.currentData())


def _celulas(mudanca) -> tuple:
    return (
        _quando(mudanca.changed_on),
        f"{mudanca.product_code} — {mudanca.product_name}".strip(" —"),
        mudanca.field.label,
        _valor(mudanca.old_price),
        _valor(mudanca.new_price),
        mudanca.changed_by or AUSENTE,
    )


def _valor(valor) -> str:
    return AUSENTE if valor is None else money_to_label(valor)


def _quando(momento) -> str:
    if momento is None:
        return AUSENTE
    return momento.astimezone().strftime("%d/%m/%Y %H:%M")
