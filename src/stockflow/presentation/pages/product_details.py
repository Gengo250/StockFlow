import qtawesome as qta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QFormLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from stockflow.presentation.styles.products import PRODUCTS_QSS


class ProductDetailsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("productDetailsPage")
        self.setStyleSheet(PRODUCTS_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(18)
        self.back_button = QPushButton("Voltar para produtos")
        self.back_button.setIcon(qta.icon("fa5s.arrow-left", color="#2563EB"))
        layout.addWidget(self.back_button, 0, Qt.AlignLeft)
        title = QLabel("Detalhes do produto")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Consulte a identificação e os valores do item · Dados demonstrativos")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.error_message = QLabel(
            "Não foi possível carregar os detalhes deste produto. "
            "Volte à listagem e selecione o produto novamente."
        )
        self.error_message.setObjectName("loadError")
        self.error_message.setWordWrap(True)
        layout.addWidget(self.error_message)

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
        fields.setVerticalSpacing(24)
        fields.setHorizontalSpacing(36)
        fields.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.values = {}
        for key, caption in (
            ("code", "Identificador"), ("name", "Nome do produto"),
            ("category", "Categoria"), ("unit", "Unidade"),
            ("sale_price", "Preço de venda"), ("cost", "Custo"),
            ("active", "Status do produto"),
        ):
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
        self.values["active"].setMaximumWidth(110)
        content_layout.addWidget(self.card)
        content_layout.addStretch()
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)
        self.load_product(None)

    def load_product(self, product):
        for value in self.values.values():
            value.clear()
        self.error_message.setVisible(product is None)
        self.scroll.setVisible(product is not None)
        if product is None:
            return
        for key, value in self.values.items():
            if key != "active":
                value.setText(getattr(product, key))
        status = self.values["active"]
        status.setText("Ativo" if product.active else "Inativo")
        foreground, background = (
            ("#166534", "#DCFCE7") if product.active else ("#475569", "#E2E8F0")
        )
        status.setStyleSheet(
            f"color: {foreground}; background: {background}; border-radius: 8px;"
            "padding: 8px 14px; font-weight: 600;"
        )
        status.setAlignment(Qt.AlignLeft)
        self.scroll.verticalScrollBar().setValue(0)
