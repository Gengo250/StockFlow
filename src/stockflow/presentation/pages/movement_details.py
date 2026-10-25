from stockflow.presentation.styles import design_system as ds

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QFormLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from stockflow.presentation.styles.products import PRODUCTS_QSS

# Mapeamento de índices da tupla de movimentação
(MOV_ID, MOV_CODE, MOV_NAME, MOV_KIND, MOV_QTY, MOV_STATUS, MOV_NOTE,
 MOV_WHEN, MOV_SUPPLIER, MOV_REASON, MOV_USER) = range(11)


class MovementDetailsPage(QWidget):
    """Página de visualização detalhada de uma movimentação de estoque (H13)."""

    back_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("movementDetailsPage")
        self.setStyleSheet(PRODUCTS_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN)
        layout.setSpacing(ds.SECTION_GAP)

        # Botão Voltar
        self.back_button = QPushButton("Voltar para movimentações")
        self.back_button.setFixedHeight(ds.CONTROL_HEIGHT)
        self.back_button.setIcon(qta.icon("fa5s.arrow-left", color="#2563EB"))
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.clicked.connect(self.back_requested.emit)
        layout.addWidget(self.back_button, 0, Qt.AlignLeft)

        # Cabeçalho
        title = QLabel("Detalhes da movimentação")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        subtitle = QLabel("Consulte os dados completos, origem e usuário responsável pela operação")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Mensagem de erro de carregamento
        self.error_message = QLabel(
            "Não foi possível carregar os detalhes desta movimentação. "
            "Volte ao histórico e selecione a movimentação novamente."
        )
        self.error_message.setObjectName("loadError")
        self.error_message.setWordWrap(True)
        layout.addWidget(self.error_message)

        # Scroll Area com os detalhes
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setObjectName("detailsCard")

        fields = QFormLayout(self.card)
        fields.setContentsMargins(24, 24, 24, 24)
        fields.setVerticalSpacing(20)
        fields.setHorizontalSpacing(36)
        fields.setRowWrapPolicy(QFormLayout.WrapLongRows)

        self.values = {}
        campos = (
            ("mov_id", "ID do Registro"),
            ("product", "Produto"),
            ("kind", "Espécie (Tipo)"),
            ("quantity", "Quantidade"),
            ("status", "Situação"),
            ("when", "Data / Hora"),
            ("origin", "Origem / Destinatário"),
            ("reason", "Motivo"),
            ("user", "Usuário Responsável"),
            ("note", "Observação / Nota"),
        )

        for key, caption in campos:
            label = QLabel(caption)
            label.setObjectName("muted")
            value = QLabel()
            value.setTextFormat(Qt.PlainText)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            value.setAccessibleName(caption)
            value.setObjectName("detailValue")
            fields.addRow(label, value)
            self.values[key] = value

        self.values["status"].setMaximumWidth(120)

        content_layout.addWidget(self.card)
        content_layout.addStretch()
        self.scroll.setWidget(content)

        layout.addWidget(self.scroll, 1)
        self.load_movement(None)

    def load_movement(self, mov):
        """Carrega e exibe a tupla da movimentação."""
        for value in self.values.values():
            value.clear()

        self.error_message.setVisible(mov is None)
        self.scroll.setVisible(mov is not None)

        if mov is None:
            return

        # Preenchimento dos campos
        self.values["mov_id"].setText(str(mov[MOV_ID]) if len(mov) > MOV_ID else "—")
        self.values["product"].setText(f"{mov[MOV_CODE]} — {mov[MOV_NAME]}")
        self.values["kind"].setText(str(mov[MOV_KIND]))
        self.values["quantity"].setText(str(mov[MOV_QTY]))
        self.values["when"].setText(str(mov[MOV_WHEN]))
        self.values["origin"].setText(str(mov[MOV_SUPPLIER]) if mov[MOV_SUPPLIER] else "—")
        self.values["reason"].setText(str(mov[MOV_REASON]) if mov[MOV_REASON] else "—")

        user_text = str(mov[MOV_USER]) if len(mov) > MOV_USER and mov[MOV_USER] else "—"
        self.values["user"].setText(user_text)

        note_text = str(mov[MOV_NOTE]) if mov[MOV_NOTE] else "—"
        self.values["note"].setText(note_text)

        # Formatação do Status
        status_label = self.values["status"]
        status_str = str(mov[MOV_STATUS])
        status_label.setText(status_str)

        if "CONFIRMADA" in status_str.upper():
            foreground, background = ("#0F7B4F", "#E4F7EF")
        elif "PENDENTE" in status_str.upper():
            foreground, background = ("#8A6A1F", "#FDF3DF")
        else:
            foreground, background = ("#8A3B3B", "#FBE9E9")

        status_label.setStyleSheet(
            ds.status_badge_qss(foreground, background)
        )
        status_label.setAlignment(Qt.AlignCenter)
        self.scroll.verticalScrollBar().setValue(0)