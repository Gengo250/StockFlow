from stockflow.presentation.styles import design_system as ds

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
        layout.setContentsMargins(ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN)
        layout.setSpacing(ds.SECTION_GAP)
        self.back_button = QPushButton("Voltar para produtos")
        self.back_button.setFixedHeight(ds.CONTROL_HEIGHT)
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
        self.supplier_label = QLabel("Fornecedor principal")
        self.supplier_label.setObjectName("muted")
        self.supplier_label.setVisible(False)
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
        supplier_value = QLabel()
        supplier_value.setTextFormat(Qt.PlainText)
        supplier_value.setWordWrap(True)
        supplier_value.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        supplier_value.setAccessibleName("Fornecedor principal")
        supplier_value.setObjectName("detailValue")
        fields.addRow(self.supplier_label, supplier_value)
        self.values["supplier"] = supplier_value
        self.values["active"].setMaximumWidth(110)
        content_layout.addWidget(self.card)
        content_layout.addStretch()
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)
        self.load_product(None)

    def load_product(self, product, *, show_supplier=False):
        for value in self.values.values():
            value.clear()
        self.current_product_code = getattr(product, "code", None)
        self.supplier_label.setVisible(bool(product is not None and show_supplier))
        self.values["supplier"].setVisible(bool(product is not None and show_supplier))
        self.error_message.setVisible(product is None)
        self.scroll.setVisible(product is not None)
        if product is None:
            return
        for key, value in self.values.items():
            if key not in ("active", "supplier"):
                value.setText(getattr(product, key))
        if show_supplier:
            self.values["supplier"].setText(
                "Carregando…" if product.supplier_id else "Não informado"
            )
        status = self.values["active"]
        status.setText("Ativo" if product.active else "Inativo")
        foreground, background = (
            ("#166534", "#DCFCE7") if product.active else ("#475569", "#E2E8F0")
        )
        status.setStyleSheet(
            ds.status_badge_qss(foreground, background)
        )
        status.setAlignment(Qt.AlignLeft)
        self.scroll.verticalScrollBar().setValue(0)

    def set_supplier_name(self, product_code, name):
        if product_code != self.current_product_code:
            return
        self.values["supplier"].setText(name or "Fornecedor não encontrado")

    def show_supplier_error(self, product_code, error):
        if product_code != self.current_product_code:
            return
        self.values["supplier"].setText(
            f"Não foi possível carregar o fornecedor: {error}"
        )
