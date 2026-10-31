"""Consulta cronológica das alterações de preço e custo (H09).

A tela é deliberadamente burra: não consulta nem ordena. Quem decide a ordem
é `fn_list_price_edits`, e reordenar aqui colocaria a mesma regra em dois
lugares — com o agravante de que o desempate do banco (pelo id da linha) não
é reproduzível fora dele.
"""

from stockflow.presentation.styles import design_system as ds

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from stockflow.infrastructure.repositories.product_mapper import money_to_label
from stockflow.presentation.styles import inventory

COLUNAS = ("Quando", "Produto", "Campo", "De", "Para", "Por")

#: Valor ausente. "antes não havia custo" não é "o custo era zero", e a tela
#: é o último lugar onde essa distinção pode ser perdida.
AUSENTE = "—"


class HistoricoPrecosPage(QWidget):

    filtro_alterado = Signal(object)

    def __init__(self):
        super().__init__()
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
        filtro = QHBoxLayout(self.filter_card)
        filtro.setContentsMargins(16, 12, 16, 12)
        filtro.setSpacing(12)
        filtro_label = QLabel("Filtrar por produto")
        filtro_label.setStyleSheet("font-weight: 600; color: #475569;")
        filtro.addWidget(filtro_label)
        filtro.addWidget(self.produto_combo, 1)

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
        self.aviso_label.hide()

        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addLayout(filtro)
        layout.addWidget(self.aviso_label)
        layout.addWidget(self.table_card, 1)

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

    def carregar(self, mudancas) -> None:
        self.aviso_label.hide()
        mudancas = tuple(mudancas)
        self.table.setRowCount(len(mudancas))
        self.empty_label.setVisible(not mudancas)
        for linha, mudanca in enumerate(mudancas):
            for coluna, texto in enumerate(_celulas(mudanca)):
                item = QTableWidgetItem(texto)
                item.setTextAlignment(
                    Qt.AlignVCenter | (Qt.AlignRight if coluna in (3, 4) else Qt.AlignLeft)
                )
                self.table.setItem(linha, coluna, item)

    def mostrar_recusa(self, erro) -> None:
        """Recusa aparece NA tela, e não num diálogo que some.

        Mesma escolha do card de ajuste: a mensagem fica ao lado do que o
        usuário tentou consultar.
        """
        self.table.setRowCount(0)
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
