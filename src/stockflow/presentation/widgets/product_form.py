import qtawesome as qta

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


LABEL_QSS = "background-color: transparent;"
FIELD_QSS = """
    {widget} {{
        background-color: #FFFFFF;
        color: #0F172A;
        border: 1px solid #CBD5E1;
        border-radius: 10px;
        padding: 0px 12px;
        font-size: 14px;
    }}
    {widget}:focus {{ border: 2px solid #93C5FD; }}
"""


def _card(object_name):
    card = QFrame()
    card.setObjectName(object_name)
    card.setStyleSheet(f"""
        QFrame#{object_name} {{
            background-color: #FFFFFF;
            border: 1px solid #DBEAFE;
            border-radius: 16px;
        }}
        QFrame#{object_name} QLabel {{ background-color: transparent; }}
    """)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 22, 22, 22)
    layout.setSpacing(16)
    return card


def _divider():
    divider = QFrame()
    divider.setFixedHeight(1)
    divider.setStyleSheet("background-color: #EFF6FF; border: none;")
    return divider


def _card_header(icon_name, title_text, subtitle_text):
    layout = QHBoxLayout()
    layout.setSpacing(12)

    icon_container = QFrame()
    icon_container.setFixedSize(38, 38)
    icon_container.setStyleSheet(
        "background-color: #EFF6FF; border: none; border-radius: 10px;"
    )
    icon_layout = QVBoxLayout(icon_container)
    icon_layout.setContentsMargins(0, 0, 0, 0)
    icon = QLabel()
    icon.setAlignment(Qt.AlignCenter)
    icon.setPixmap(qta.icon(icon_name, color="#2563EB").pixmap(16, 16))
    icon_layout.addWidget(icon)

    text_container = QWidget()
    text_layout = QVBoxLayout(text_container)
    text_layout.setContentsMargins(0, 0, 0, 0)
    text_layout.setSpacing(2)
    title = QLabel(title_text)
    title.setStyleSheet(
        f"{LABEL_QSS} color: #0F172A; font-size: 16px; font-weight: 600;"
    )
    subtitle = QLabel(subtitle_text)
    subtitle.setStyleSheet(f"{LABEL_QSS} color: #94A3B8; font-size: 12px;")
    text_layout.addWidget(title)
    text_layout.addWidget(subtitle)

    layout.addWidget(icon_container)
    layout.addWidget(text_container)
    layout.addStretch()
    return layout


def _field(label_text, optional=False):
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    label_row = QHBoxLayout()
    label = QLabel(label_text)
    label.setStyleSheet(
        f"{LABEL_QSS} color: #475569; font-size: 13px; font-weight: 500;"
    )
    label_row.addWidget(label)
    if optional:
        optional_label = QLabel("(opcional)")
        optional_label.setStyleSheet(
            f"{LABEL_QSS} color: #94A3B8; font-size: 12px;"
        )
        label_row.addWidget(optional_label)
    label_row.addStretch()
    layout.addLayout(label_row)
    return container


def _line_edit(placeholder=""):
    widget = QLineEdit()
    widget.setPlaceholderText(placeholder)
    widget.setFixedHeight(42)
    widget.setStyleSheet(FIELD_QSS.format(widget="QLineEdit"))
    return widget


def _combo(items):
    widget = QComboBox()
    widget.addItems(items)
    widget.setFixedHeight(42)
    widget.setStyleSheet(
        FIELD_QSS.format(widget="QComboBox")
        + "QComboBox::drop-down { border: none; width: 30px; }"
    )
    return widget


def _money_input():
    widget = QDoubleSpinBox()
    widget.setRange(0, 99999999)
    widget.setDecimals(2)
    widget.setSingleStep(1)
    widget.setPrefix("R$ ")
    widget.setFixedHeight(42)
    widget.setStyleSheet(
        FIELD_QSS.format(widget="QDoubleSpinBox")
        + "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button "
          "{ width: 20px; border: none; background-color: transparent; }"
    )
    return widget


def _stock_input():
    widget = QSpinBox()
    widget.setRange(0, 999999)
    widget.setSingleStep(1)
    widget.setFixedHeight(42)
    widget.setStyleSheet(
        FIELD_QSS.format(widget="QSpinBox")
        + "QSpinBox::up-button, QSpinBox::down-button "
          "{ width: 20px; border: none; background-color: transparent; }"
    )
    return widget


class BasicInfoCard(QFrame):
    def __init__(self):
        super().__init__()
        card = _card("basicInfoCard")
        layout = card.layout()
        layout.addLayout(_card_header(
            "fa5s.box",
            "Informações básicas",
            "Dados de identificação e classificação do produto.",
        ))
        layout.addWidget(_divider())

        name = _field("Nome do produto")
        self.name_input = _line_edit('Ex.: Monitor LG UltraWide 34"')
        name.layout().addWidget(self.name_input)
        layout.addWidget(name)

        row = QHBoxLayout()
        row.setSpacing(16)
        sku = _field("Código / SKU")
        sku_wrapper = QFrame()
        sku_wrapper.setObjectName("skuWrapper")
        sku_wrapper.setFixedHeight(42)
        sku_wrapper.setStyleSheet("""
            QFrame#skuWrapper {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 10px;
            }
            QFrame#skuWrapper QLabel { background-color: transparent; }
        """)
        sku_layout = QHBoxLayout(sku_wrapper)
        sku_layout.setContentsMargins(12, 0, 12, 0)
        sku_layout.setSpacing(8)
        self.code_input = QLineEdit("PRD-009")
        self.code_input.setReadOnly(True)
        self.code_input.setStyleSheet(
            "background-color: transparent; color: #334155; border: none; font-size: 14px;"
        )
        automatic = QLabel("Automático")
        automatic.setStyleSheet(f"{LABEL_QSS} color: #2563EB; font-size: 12px;")
        sku_layout.addWidget(self.code_input, 1)
        sku_layout.addWidget(automatic)
        sku.layout().addWidget(sku_wrapper)

        category = _field("Categoria")
        self.category_input = _combo(["Selecione uma categoria"])
        category.layout().addWidget(self.category_input)
        row.addWidget(sku)
        row.addWidget(category)
        layout.addLayout(row)

        description = _field("Descrição", optional=True)
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText(
            "Descreva as principais características do produto..."
        )
        self.description_input.setFixedHeight(100)
        self.description_input.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #CBD5E1;
                border-radius: 10px;
                padding: 10px;
                font-size: 14px;
            }
            QTextEdit:focus { border: 2px solid #93C5FD; }
        """)
        self.description_counter = QLabel("0 / 500 caracteres")
        self.description_counter.setAlignment(Qt.AlignRight)
        self.description_counter.setStyleSheet(
            f"{LABEL_QSS} color: #94A3B8; font-size: 11px;"
        )
        description.layout().addWidget(self.description_input)
        description.layout().addWidget(self.description_counter)
        layout.addWidget(description)
        self.description_input.textChanged.connect(self._update_counter)

        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(card)

    def _update_counter(self):
        text = self.description_input.toPlainText()
        if len(text) > 500:
            text = text[:500]
            self.description_input.blockSignals(True)
            self.description_input.setPlainText(text)
            cursor = self.description_input.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.description_input.setTextCursor(cursor)
            self.description_input.blockSignals(False)
        self.description_counter.setText(f"{len(text)} / 500 caracteres")


class PriceTaxCard(QFrame):
    def __init__(self):
        super().__init__()
        card = _card("priceTaxCard")
        layout = card.layout()
        layout.addLayout(_card_header(
            "fa5s.dollar-sign",
            "Preço e tributação",
            "Defina os valores de custo, venda e dados fiscais.",
        ))
        layout.addWidget(_divider())

        first_row = QHBoxLayout()
        first_row.setSpacing(16)
        cost = _field("Preço de custo")
        self.cost_price_input = _money_input()
        cost.layout().addWidget(self.cost_price_input)
        sale = _field("Preço de venda")
        self.sale_price_input = _money_input()
        sale.layout().addWidget(self.sale_price_input)
        unit = _field("Unidade")
        self.unit_input = _combo([
            "Unidade (UN)", "Caixa (CX)", "Pacote (PCT)",
            "Quilograma (KG)", "Grama (G)", "Litro (L)", "Metro (M)",
        ])
        unit.layout().addWidget(self.unit_input)
        first_row.addWidget(cost)
        first_row.addWidget(sale)
        first_row.addWidget(unit)
        layout.addLayout(first_row)

        second_row = QHBoxLayout()
        second_row.setSpacing(16)
        ncm = _field("NCM", optional=True)
        self.ncm_input = _line_edit("0000.00.00")
        ncm.layout().addWidget(self.ncm_input)
        ean = _field("Código de barras / EAN", optional=True)
        self.ean_input = _line_edit("7890000000000")
        ean.layout().addWidget(self.ean_input)
        second_row.addWidget(ncm)
        second_row.addWidget(ean)
        layout.addLayout(second_row)

        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(card)


class StockControlCard(QFrame):
    def __init__(self):
        super().__init__()
        card = _card("stockControlCard")
        layout = card.layout()
        layout.addLayout(_card_header(
            "fa5s.boxes",
            "Controle de estoque",
            "Defina quantidades, limites e localização do item.",
        ))
        layout.addWidget(_divider())

        row = QHBoxLayout()
        row.setSpacing(16)
        initial = _field("Estoque inicial")
        self.initial_stock_input = _stock_input()
        initial.layout().addWidget(self.initial_stock_input)
        minimum = _field("Estoque mínimo")
        self.minimum_stock_input = _stock_input()
        minimum.layout().addWidget(self.minimum_stock_input)
        location = _field("Localização", optional=True)
        self.location_input = _line_edit("Ex.: Corredor A - Prateleira 3")
        location.layout().addWidget(self.location_input)
        row.addWidget(initial)
        row.addWidget(minimum)
        row.addWidget(location)
        layout.addLayout(row)

        supplier = _field("Fornecedor principal", optional=True)
        self.supplier_input = _combo(["Selecione um fornecedor"])
        supplier.layout().addWidget(self.supplier_input)
        layout.addWidget(supplier)

        alert = QFrame()
        alert.setObjectName("stockAlertContainer")
        alert.setStyleSheet("""
            QFrame#stockAlertContainer {
                background-color: #F8FBFF;
                border: 1px solid #DBEAFE;
                border-radius: 12px;
            }
            QFrame#stockAlertContainer QLabel { background-color: transparent; }
        """)
        alert_layout = QHBoxLayout(alert)
        alert_layout.setContentsMargins(14, 12, 14, 12)
        alert_layout.setSpacing(12)
        self.low_stock_alert = QCheckBox()
        self.low_stock_alert.setChecked(True)
        self.low_stock_alert.setCursor(Qt.PointingHandCursor)
        texts = QWidget()
        texts_layout = QVBoxLayout(texts)
        texts_layout.setContentsMargins(0, 0, 0, 0)
        texts_layout.setSpacing(2)
        title = QLabel("Avisar quando o estoque estiver baixo")
        title.setStyleSheet(
            f"{LABEL_QSS} color: #334155; font-size: 13px; font-weight: 600;"
        )
        subtitle = QLabel(
            "Você receberá uma notificação quando o estoque atingir o limite mínimo definido."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"{LABEL_QSS} color: #94A3B8; font-size: 12px;")
        texts_layout.addWidget(title)
        texts_layout.addWidget(subtitle)
        alert_layout.addWidget(self.low_stock_alert, 0, Qt.AlignTop)
        alert_layout.addWidget(texts, 1)
        layout.addWidget(alert)

        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(card)


class ProductStatusCard(QFrame):
    def __init__(self):
        super().__init__()
        card = _card("productStatusCard")
        layout = card.layout()
        header = QHBoxLayout()
        header.setSpacing(12)
        texts = QWidget()
        texts_layout = QVBoxLayout(texts)
        texts_layout.setContentsMargins(0, 0, 0, 0)
        texts_layout.setSpacing(3)
        title = QLabel("Status do produto")
        title.setStyleSheet(
            f"{LABEL_QSS} color: #0F172A; font-size: 16px; font-weight: 600;"
        )
        subtitle = QLabel("Disponível para vendas e movimentações.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"{LABEL_QSS} color: #94A3B8; font-size: 12px;")
        texts_layout.addWidget(title)
        texts_layout.addWidget(subtitle)

        self.product_status_toggle = QPushButton()
        self.product_status_toggle.setCheckable(True)
        self.product_status_toggle.setChecked(True)
        self.product_status_toggle.setCursor(Qt.PointingHandCursor)
        self.product_status_toggle.setFixedSize(46, 24)
        self.product_status_toggle.setStyleSheet("""
            QPushButton { background-color: #CBD5E1; border: none; border-radius: 12px; }
            QPushButton:checked { background-color: #2563EB; }
        """)
        header.addWidget(texts, 1)
        header.addWidget(self.product_status_toggle, 0, Qt.AlignTop)
        layout.addLayout(header)
        layout.addWidget(_divider())

        status = QHBoxLayout()
        status.setSpacing(8)
        self.status_dot = QLabel("●")
        self.status_label = QLabel("Ativo")
        status.addWidget(self.status_dot)
        status.addWidget(self.status_label)
        status.addStretch()
        layout.addLayout(status)
        self.product_status_toggle.toggled.connect(self._update_status)
        self._update_status(True)

        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(card)

    def _update_status(self, checked):
        dot_color = "#22C55E" if checked else "#94A3B8"
        text_color = "#166534" if checked else "#64748B"
        self.status_dot.setStyleSheet(
            f"{LABEL_QSS} color: {dot_color}; font-size: 11px;"
        )
        self.status_label.setText("Ativo" if checked else "Inativo")
        self.status_label.setStyleSheet(
            f"{LABEL_QSS} color: {text_color}; font-size: 13px; font-weight: 600;"
        )


class BeforeRegisterCard(QFrame):
    TIPS = (
        ("fa5s.barcode", "Verifique se o SKU e o código de barras estão corretos."),
        ("fa5s.dollar-sign", "Confirme o preço de venda e os dados fiscais."),
        ("fa5s.boxes", "Defina um estoque mínimo adequado para receber alertas."),
    )

    def __init__(self):
        super().__init__()
        self.setObjectName("beforeRegisterCard")
        self.setStyleSheet("""
            QFrame#beforeRegisterCard {
                background-color: #EFF6FF;
                border: 1px solid #BFDBFE;
                border-radius: 16px;
            }
            QFrame#beforeRegisterCard QLabel { background-color: transparent; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)
        icon = QLabel()
        icon.setFixedSize(34, 34)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            "background-color: #DBEAFE; border: none; border-radius: 9px;"
        )
        icon.setPixmap(qta.icon("fa5s.info-circle", color="#2563EB").pixmap(15, 15))
        title = QLabel("Antes de cadastrar")
        title.setStyleSheet(
            f"{LABEL_QSS} color: #1E3A8A; font-size: 15px; font-weight: 600;"
        )
        header.addWidget(icon)
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        message = QLabel("Confira as informações do produto antes de concluir o cadastro.")
        message.setWordWrap(True)
        message.setStyleSheet(f"{LABEL_QSS} color: #475569; font-size: 12px;")
        layout.addWidget(message)
        for icon_name, text in self.TIPS:
            layout.addWidget(self._tip(icon_name, text))

    @staticmethod
    def _tip(icon_name, text):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        icon = QLabel()
        icon.setFixedSize(18, 18)
        icon.setAlignment(Qt.AlignTop)
        icon.setPixmap(qta.icon(icon_name, color="#3B82F6").pixmap(13, 13))
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"{LABEL_QSS} color: #64748B; font-size: 12px;")
        layout.addWidget(icon, 0, Qt.AlignTop)
        layout.addWidget(label, 1)
        return container


class ProductImageCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(170)
        self.setStyleSheet("""
            ProductImageCard {
                background-color: #FFFFFF;
                border: 1px solid #DBEAFE;
                border-radius: 16px;
            }
            ProductImageCard QLabel { background-color: transparent; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        label = QLabel("Imagem do produto")
        label.setStyleSheet(
            f"{LABEL_QSS} color: #0F172A; font-size: 16px; font-weight: 600; border: none;"
        )
        layout.addWidget(label)
        layout.addStretch()
