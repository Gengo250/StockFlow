import qtawesome as qta

from PySide6.QtCore import Qt, QBuffer, QIODevice
from PySide6.QtGui import QTextCursor, QImage, QPixmap, QImageReader
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QMessageBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from stockflow.domain.enums.product_unit import PRODUCT_UNITS
from stockflow.presentation.widgets.form_fields import (
    FormCard, LABEL_QSS, _card_header, _combo, _divider, _field,
    _line_edit, _minimum_stock_input, _money_input, _stock_input,
)


class BasicInfoCard(FormCard):
    def __init__(self):
        super().__init__("basicInfoCard")
        layout = self.content_layout
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
        # Nasce vazio: o SKU é gerado a partir do catálogo quando a página é
        # aberta (`MainWindow._show_new_product` -> `set_code`) ou vem do
        # produto carregado na edição. O valor fixo que ficava aqui era um
        # código de produto REAL do catálogo, então todo cadastro colidia com
        # ele e morria em "Já existe um produto com o código PRD-009".
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Gerado automaticamente")
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
        # O combo só lista o que já existe. Numa empresa recém-criada ele vem
        # vazio, e como o cadastro exige categoria o primeiro produto ficava
        # impossível de registrar pela tela. Este botão é a única porta de
        # `fn_create_categories` na interface.
        category_row = QHBoxLayout()
        category_row.setSpacing(8)
        self.category_input = _combo(["Selecione uma categoria"])
        self.new_category_button = QPushButton("Nova")
        self.new_category_button.setObjectName("secondaryButton")
        self.new_category_button.setToolTip("Cadastrar uma categoria nesta empresa")
        self.new_category_button.setFixedHeight(self.category_input.sizeHint().height())
        category_row.addWidget(self.category_input, 1)
        category_row.addWidget(self.new_category_button)
        category.layout().addLayout(category_row)
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


class PriceTaxCard(FormCard):
    def __init__(self):
        super().__init__("priceTaxCard")
        layout = self.content_layout
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
        self.unit_input = _combo(PRODUCT_UNITS)
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



class StockControlCard(FormCard):
    def __init__(self):
        super().__init__("stockControlCard")
        layout = self.content_layout
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
        minimum = _field("Estoque mínimo", optional=True)
        self.minimum_stock_input = _minimum_stock_input()
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



class ProductStatusCard(FormCard):
    def __init__(self):
        super().__init__("productStatusCard")
        layout = self.content_layout
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
    """Miniatura JPEG limitada, persistida junto ao produto."""
    def __init__(self):
        super().__init__()
        self.image_data = ""
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Imagem do produto"))
        self.preview = QLabel("Sem imagem")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(160)
        layout.addWidget(self.preview)
        self.choose_button = QPushButton("Selecionar imagem")
        self.remove_button = QPushButton("Remover imagem")
        layout.addWidget(self.choose_button)
        layout.addWidget(self.remove_button)
        self.choose_button.clicked.connect(self.choose_image)
        self.remove_button.clicked.connect(lambda: self.set_image_data(""))

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Imagem do produto", "", "Imagens (*.png *.jpg *.jpeg *.webp)")
        if path:
            try:
                self.load_image(path)
            except ValueError as error:
                QMessageBox.warning(self, "Imagem inválida", str(error))

    def load_image(self, path):
        from pathlib import Path
        import base64
        if Path(path).stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Selecione uma imagem de até 10 MB.")
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.width() * size.height() > 40_000_000:
            raise ValueError("Imagem excede o limite de 40 megapixels.")
        image = reader.read()
        if image.isNull():
            raise ValueError("Não foi possível ler esta imagem.")
        image = image.scaled(512, 512, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not image.save(buffer, "JPEG", 80):
            raise ValueError("Não foi possível preparar a imagem.")
        encoded = base64.b64encode(bytes(buffer.data())).decode("ascii")
        if len(encoded) > 350000:
            raise ValueError("Imagem muito grande após a conversão.")
        self.set_image_data(encoded)

    def set_image_data(self, value):
        import base64
        self.image_data = value or ""
        image = QImage()
        try:
            image.loadFromData(base64.b64decode(self.image_data, validate=True))
        except (ValueError, TypeError):
            pass
        if image.isNull():
            self.preview.clear()
            self.preview.setText("Sem imagem")
        else:
            self.preview.setPixmap(QPixmap.fromImage(image).scaled(240, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
