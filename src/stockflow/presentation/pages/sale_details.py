"""Detalhe de uma venda, com as operações que a desfazem (US17/SCRUM-221).

As ações de cancelar e devolver moram AQUI, e não na listagem. Obrigar o
administrador a abrir a venda antes de revertê-la é a distinção entre
consultar e operar que o SCRUM-223 pede, e tira a ação destrutiva de uma
tabela densa onde ela ficaria a um clique de distância da linha errada.
"""

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stockflow.application.dto.sale_filter import MOTIVO_MAXIMO
from stockflow.domain.enums.sale_reversal_kind import SaleReversalKind
from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.domain.permissions import can_reverse_sales
from stockflow.presentation.styles import inventory
from stockflow.presentation.widgets.form_fields import _card, _card_header

CORES_DE_STATUS = {
    SaleStatus.CONCLUIDA.label: ("#166534", "#DCFCE7"),
    SaleStatus.CANCELADA.label: ("#8A3B3B", "#FBE9E9"),
    SaleStatus.DEVOLVIDA.label: ("#92400E", "#FEF3C7"),
    SaleStatus.PENDENTE.label: ("#334155", "#E2E8F0"),
}

ITEM_COLUNAS = [
    "Código", "Produto", "Qtd.", "Preço unitário", "Subtotal",
    "Desconto", "Subtotal final",
]


def _moeda(valor) -> str:
    """"12.5" -> "R$ 12,50". O valor vem como texto do banco."""
    try:
        numero = float(str(valor).replace("R$", "").strip() or 0)
    except ValueError:
        return str(valor)
    texto = f"{numero:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


class SaleDetailsPage(QWidget):
    """Itens, valores, pagamento, responsável e vínculo de reversão."""

    back_requested = Signal()
    #: (identificador, motivo) — a tela não reverte sozinha; quem decide e
    #: trata a recusa é a janela, que também precisa atualizar o estoque.
    cancel_requested = Signal(str, str)
    return_requested = Signal(str, str)
    #: Identificador da venda cujo comprovante foi pedido (US19). A página
    #: não monta o documento: quem o monta é o serviço, que a janela já tem.
    receipt_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("saleDetailsPage")
        self.setStyleSheet(
            "QWidget#saleDetailsPage { background: #F0F5FF; }"
            " QLabel { background: transparent; color: #334155; }"
        )
        self.venda = None
        self.session = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(18)

        self.back_button = QPushButton("Voltar para vendas")
        self.back_button.setIcon(qta.icon("fa5s.arrow-left", color="#2563EB"))
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.setStyleSheet(inventory.FILTER_QSS)
        self.back_button.setFixedHeight(38)
        self.back_button.clicked.connect(self.back_requested.emit)
        layout.addWidget(self.back_button, 0, Qt.AlignLeft)

        titulo = QLabel("Detalhes da venda")
        titulo.setStyleSheet(inventory.TITLE_QSS)
        layout.addWidget(titulo)

        self.error_label = QLabel(
            "Não foi possível carregar os detalhes desta venda. "
            "Volte ao histórico e selecione a venda novamente."
        )
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(inventory.LOAD_ERROR_QSS)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        corpo = QScrollArea()
        corpo.setWidgetResizable(True)
        corpo.setFrameShape(QFrame.NoFrame)
        conteudo = QWidget()
        conteudo_layout = QVBoxLayout(conteudo)
        conteudo_layout.setContentsMargins(0, 0, 0, 0)
        conteudo_layout.setSpacing(16)

        conteudo_layout.addWidget(self._criar_resumo())
        conteudo_layout.addWidget(self._criar_itens())
        conteudo_layout.addWidget(self._criar_reversao())
        conteudo_layout.addStretch()
        corpo.setWidget(conteudo)
        layout.addWidget(corpo, 1)

        layout.addLayout(self._criar_acoes())

    # ------------------------------------------------------------ montagem

    def _criar_resumo(self):
        card = _card("saleSummary")
        card.layout().addLayout(
            _card_header("fa5s.receipt", "Resumo", "Cliente, responsável e pagamento.")
        )
        self.resumo_label = QLabel()
        self.resumo_label.setWordWrap(True)
        self.resumo_label.setTextFormat(Qt.RichText)
        card.layout().addWidget(self.resumo_label)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFixedWidth(130)
        self.status_label.setFixedHeight(28)
        card.layout().addWidget(self.status_label, 0, Qt.AlignLeft)
        return card

    def _criar_itens(self):
        card = _card("saleItems")
        card.layout().addLayout(
            _card_header(
                "fa5s.boxes",
                "Itens da venda",
                "Quantidades e preços como foram gravados na operação.",
            )
        )
        self.itens_table = QTableWidget()
        self.itens_table.setColumnCount(len(ITEM_COLUNAS))
        self.itens_table.setHorizontalHeaderLabels(ITEM_COLUNAS)
        self.itens_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.itens_table.setStyleSheet(inventory.TABLE_QSS)
        # Consultar não é editar: o SCRUM-223 vale aqui como vale na listagem.
        self.itens_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.itens_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.itens_table.verticalHeader().hide()
        self.itens_table.setShowGrid(False)
        self.itens_table.verticalHeader().setDefaultSectionSize(40)
        card.layout().addWidget(self.itens_table)

        self.totais_label = QLabel()
        self.totais_label.setTextFormat(Qt.RichText)
        self.totais_label.setAlignment(Qt.AlignRight)
        self.totais_label.setStyleSheet(
            "color: #0F172A; font-size: 14px; font-weight: 600;"
        )
        card.layout().addWidget(self.totais_label)
        return card

    def _criar_reversao(self):
        self.reversao_card = _card("saleReversal")
        self.reversao_card.layout().addLayout(
            _card_header(
                "fa5s.undo",
                "Operação de reversão",
                "Vínculo entre esta venda e a operação que a desfez.",
            )
        )
        self.reversao_label = QLabel()
        self.reversao_label.setWordWrap(True)
        self.reversao_label.setTextFormat(Qt.RichText)
        self.reversao_card.layout().addWidget(self.reversao_label)
        self.reversao_card.setVisible(False)
        return self.reversao_card

    def _criar_acoes(self):
        linha = QHBoxLayout()
        linha.addStretch()
        self.receipt_button = QPushButton("Emitir comprovante")
        self.receipt_button.setIcon(qta.icon("fa5s.file-invoice", color="#2563EB"))
        self.receipt_button.setAccessibleName("Emitir o comprovante desta venda")
        self.receipt_button.clicked.connect(self._pedir_comprovante)
        self.cancel_button = QPushButton("Cancelar venda")
        self.cancel_button.setIcon(qta.icon("fa5s.ban", color="#B91C1C"))
        self.cancel_button.setAccessibleName("Cancelar esta venda")
        self.cancel_button.clicked.connect(self._pedir_cancelamento)
        self.return_button = QPushButton("Registrar devolução")
        self.return_button.setIcon(qta.icon("fa5s.undo", color="#B45309"))
        self.return_button.setAccessibleName("Registrar devolução desta venda")
        self.return_button.clicked.connect(self._pedir_devolucao)
        for botao in (self.receipt_button, self.cancel_button, self.return_button):
            botao.setFixedHeight(40)
            botao.setCursor(Qt.PointingHandCursor)
            botao.setStyleSheet(inventory.NEW_BUTTON_QSS)
            linha.addWidget(botao)
        return linha

    # --------------------------------------------------------------- carga

    def load_sale(self, venda, session=None):
        """Desenha a venda. `None` mostra o aviso em vez de uma tela vazia."""
        self.venda = venda
        self.session = session
        if not venda:
            self.error_label.setVisible(True)
            self.itens_table.setRowCount(0)
            self.resumo_label.setText("")
            self.totais_label.setText("")
            self.status_label.setText("")
            self.reversao_card.setVisible(False)
            for botao in (self.receipt_button, self.cancel_button,
                          self.return_button):
                botao.setEnabled(False)
            return

        self.error_label.setVisible(False)
        self._desenhar_resumo(venda)
        self._desenhar_itens(venda)
        self._desenhar_reversao(venda)
        self._aplicar_alcada(venda, session)

    def resumo_text(self) -> str:
        """Texto plano do resumo, para teste e leitor de tela."""
        return self.resumo_label.text()

    def _desenhar_resumo(self, venda):
        situacao = SaleStatus.from_value(venda.get("status") or "CONCLUIDA")
        cor, fundo = CORES_DE_STATUS[situacao.label]
        self.status_label.setText(situacao.label)
        self.status_label.setStyleSheet(
            f"color: {cor}; background: {fundo}; border-radius: 14px;"
            " font-size: 13px; font-weight: 600;"
        )
        # Responsável vazio vira travessão, e não string vazia: campo em
        # branco parece defeito de carga; travessão diz "não há".
        vendedor = venda.get("seller") or "—"
        desconto_aplicado_por = venda.get("discount_applied_by_name") or vendedor
        autorizador = venda.get("discount_authorized_by_name") or "—"
        self.resumo_label.setText(
            f"<b>Venda:</b> {venda.get('id', '—')}<br>"
            f"<b>Cliente:</b> {venda.get('cliente', '—')}<br>"
            f"<b>Responsável:</b> {vendedor}<br>"
            f"<b>Data:</b> {venda.get('data', '—')}<br>"
            f"<b>Forma de pagamento:</b> {venda.get('payment_method') or '—'}<br>"
            f"<b>Desconto aplicado por:</b> {desconto_aplicado_por}<br>"
            f"<b>Desconto autorizado por:</b> {autorizador}"
        )

    def _desenhar_itens(self, venda):
        itens = venda.get("items") or []
        self.itens_table.setRowCount(len(itens))
        bruto = 0.0
        for linha, item in enumerate(itens):
            quantidade = int(item.get("quantity", 0) or 0)
            unitario = item.get("unit_price")
            subtotal = item.get("subtotal")
            # `fn_register_sale` devolve o item sem preço; `fn_list_sales`
            # devolve com. O detalhe mostra o que existe e não inventa o que
            # falta — zero aqui seria uma afirmação falsa sobre o preço.
            valores = [
                str(item.get("product_code") or "—"),
                str(item.get("product_name") or "—"),
                str(quantidade),
                _moeda(unitario) if unitario is not None else "—",
                _moeda(subtotal) if subtotal is not None else "—",
                _moeda(item.get("discount_amount") or "0"),
                _moeda(item.get("final_subtotal", subtotal or "0")),
            ]
            for coluna, texto in enumerate(valores):
                celula = QTableWidgetItem(texto)
                if coluna >= 2:
                    celula.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.itens_table.setItem(linha, coluna, celula)
            if subtotal is not None:
                try:
                    bruto += float(str(subtotal))
                except ValueError:
                    pass

        desconto = venda.get("discount") or "0"
        self.totais_label.setText(
            f"Bruto: {_moeda(bruto)} &nbsp;·&nbsp; "
            f"Desconto: {_moeda(desconto)} &nbsp;·&nbsp; "
            f"<span style='font-size:16px'>Total: "
            f"{venda.get('valor') or _moeda(venda.get('total'))}</span>"
        )

    def _desenhar_reversao(self, venda):
        especie = venda.get("reversal_kind")
        if not especie:
            self.reversao_card.setVisible(False)
            return
        rotulo = SaleReversalKind.from_value(especie).label
        autor = venda.get("reversal_by") or "—"
        quando = venda.get("reversal_on") or "—"
        self.reversao_label.setText(
            f"<b>Operação:</b> {rotulo}<br>"
            f"<b>Motivo:</b> {venda.get('reversal_reason') or '—'}<br>"
            f"<b>Responsável:</b> {autor}<br>"
            f"<b>Quando:</b> {quando}"
        )
        self.reversao_card.setVisible(True)

    def _aplicar_alcada(self, venda, session):
        """Botão desabilitado é cortesia visual; a decisão é do domínio.

        A recusa real acontece no serviço e de novo no banco. Isto aqui só
        evita oferecer ao usuário uma ação que ele levaria recusa ao tentar.
        """
        situacao = SaleStatus.from_value(venda.get("status") or "CONCLUIDA")
        pode_reverter = can_reverse_sales(session)
        for botao in (self.cancel_button, self.return_button):
            # Quem não tem alçada não vê o botão: desabilitado ainda sugere
            # que a operação é dele e que falta alguma condição.
            botao.setVisible(pode_reverter)
            botao.setEnabled(pode_reverter and situacao.reversivel)
        if pode_reverter and not situacao.reversivel:
            dica = f"Venda {situacao.label.lower()}: não há o que reverter."
            for botao in (self.cancel_button, self.return_button):
                botao.setToolTip(dica)

        # Comprovante é LEITURA: quem abre o detalhe pode emitir, inclusive
        # o vendedor que não tem alçada para reverter. O que o status decide
        # é outra coisa — venda pendente nunca foi confirmada, então não há
        # operação a comprovar (SCRUM-227). Cancelada tem comprovante, e ele
        # sai marcado (SCRUM-229).
        emitivel = situacao is not SaleStatus.PENDENTE
        self.receipt_button.setEnabled(emitivel)
        self.receipt_button.setToolTip(
            "Emitir o comprovante desta venda" if emitivel
            else "Esta venda ainda não foi confirmada."
        )

    # --------------------------------------------------------------- ações

    def _pedir_motivo(self, titulo, rotulo):
        """O motivo é obrigatório, e a recusa acontece antes de emitir nada."""
        texto, confirmou = QInputDialog.getText(self, titulo, rotulo)
        if not confirmou:
            return None
        texto = (texto or "").strip()
        if not texto:
            QMessageBox.warning(self, titulo, "Informe o motivo da operação.")
            return None
        if len(texto) > MOTIVO_MAXIMO:
            QMessageBox.warning(
                self,
                titulo,
                f"O motivo deve ter no máximo {MOTIVO_MAXIMO} caracteres.",
            )
            return None
        return texto

    def _pedir_comprovante(self):
        if self.venda:
            self.receipt_requested.emit(str(self.venda["id"]))

    def _pedir_cancelamento(self):
        if not self.venda:
            return
        motivo = self._pedir_motivo(
            "Cancelar venda", "Por que esta venda está sendo cancelada?"
        )
        if motivo:
            self.cancel_requested.emit(str(self.venda["id"]), motivo)

    def _pedir_devolucao(self):
        if not self.venda:
            return
        motivo = self._pedir_motivo(
            "Registrar devolução", "Por que esta venda está sendo devolvida?"
        )
        if motivo:
            self.return_requested.emit(str(self.venda["id"]), motivo)
