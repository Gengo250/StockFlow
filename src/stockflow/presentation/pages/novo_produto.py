import qtawesome as qta

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QLineEdit,
    QComboBox,
    QTextEdit,
    QDoubleSpinBox,
)

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QTextCursor


class NovoProdutoPage(QWidget):

    def __init__(self):
        super().__init__()

        self.setObjectName("novoProdutoPage")

        self.setStyleSheet("""
            QWidget#novoProdutoPage {
                background-color: #F0F5FF;
            }
        """)

        # ==================================================
        # LAYOUT PRINCIPAL
        # ==================================================

        page_layout = QVBoxLayout(self)

        page_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        page_layout.setSpacing(0)

        # ==================================================
        # SCROLL AREA
        # ==================================================

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setFrameShape(
            QFrame.NoFrame
        )

        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        scroll.setStyleSheet("""
            QScrollArea {
                background-color: #F0F5FF;
                border: none;
            }

            QScrollArea > QWidget > QWidget {
                background-color: #F0F5FF;
            }

            QScrollBar:vertical {
                background: transparent;

                width: 8px;

                margin: 4px 2px 4px 2px;
            }

            QScrollBar::handle:vertical {
                background: #CBD5E1;

                border-radius: 4px;

                min-height: 30px;
            }

            QScrollBar::handle:vertical:hover {
                background: #94A3B8;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # ==================================================
        # CONTEÚDO INTERNO
        # ==================================================

        content = QWidget()

        content.setObjectName(
            "novoProdutoContent"
        )

        content.setStyleSheet("""
            QWidget#novoProdutoContent {
                background-color: #F0F5FF;
            }
        """)

        content_layout = QVBoxLayout(
            content
        )

        content_layout.setContentsMargins(
            20,
            20,
            20,
            30
        )

        content_layout.setSpacing(
            22
        )

        # ==================================================
        # HEADER
        # ==================================================

        content_layout.addWidget(
            self._create_header()
        )

        # ==================================================
        # DUAS COLUNAS
        # ==================================================

        columns_layout = QHBoxLayout()

        columns_layout.setSpacing(
            20
        )

        columns_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        # ==================================================
        # COLUNA ESQUERDA
        # ==================================================

        left_column = QWidget()

        left_layout = QVBoxLayout(
            left_column
        )

        left_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        left_layout.setSpacing(
            18
        )

        left_layout.addWidget(
            self._create_basic_info_card()
        )

        left_layout.addWidget(
            self._create_price_tax_card()
        )

        left_layout.addWidget(
            self._placeholder_card(
                "Controle de estoque"
            )
        )

        left_layout.addStretch()

        # ==================================================
        # COLUNA DIREITA
        # ==================================================

        right_column = QWidget()

        right_layout = QVBoxLayout(
            right_column
        )

        right_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        right_layout.setSpacing(
            18
        )

        right_layout.addWidget(
            self._placeholder_card(
                "Imagem do produto"
            )
        )

        right_layout.addWidget(
            self._placeholder_card(
                "Status do produto"
            )
        )

        right_layout.addWidget(
            self._placeholder_card(
                "Antes de cadastrar"
            )
        )

        right_layout.addStretch()

        columns_layout.addWidget(
            left_column,
            2
        )

        columns_layout.addWidget(
            right_column,
            1
        )

        content_layout.addLayout(
            columns_layout
        )

        # ==================================================
        # FINALIZA SCROLL
        # ==================================================

        scroll.setWidget(
            content
        )

        page_layout.addWidget(
            scroll
        )

    # ======================================================
    # HEADER
    # ======================================================

    def _create_header(self):

        header = QWidget()

        layout = QHBoxLayout(
            header
        )

        layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        layout.setSpacing(
            12
        )

        # --------------------------------------------------
        # ESQUERDA
        # --------------------------------------------------

        left = QWidget()

        left_layout = QVBoxLayout(
            left
        )

        left_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        left_layout.setSpacing(
            4
        )

        self.back_button = QPushButton(
            "Produtos"
        )

        self.back_button.setIcon(
            qta.icon(
                "fa5s.chevron-left",
                color="#64748B"
            )
        )

        self.back_button.setIconSize(
            QSize(10, 10)
        )

        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;

                color: #64748B;

                border: none;

                text-align: left;

                padding: 0px;

                font-size: 13px;
            }

            QPushButton:hover {
                color: #2563EB;
            }
        """)

        title = QLabel(
            "Cadastrar novo produto"
        )

        title.setStyleSheet("""
            color: #0F172A;

            font-size: 26px;
            font-weight: 700;
        """)

        subtitle = QLabel(
            "Adicione as informações comerciais "
            "e de estoque do item."
        )

        subtitle.setStyleSheet("""
            color: #64748B;

            font-size: 14px;
        """)

        left_layout.addWidget(
            self.back_button,
            alignment=Qt.AlignLeft
        )

        left_layout.addSpacing(
            6
        )

        left_layout.addWidget(
            title
        )

        left_layout.addWidget(
            subtitle
        )

        # --------------------------------------------------
        # DIREITA
        # --------------------------------------------------

        actions = QWidget()

        actions_layout = QHBoxLayout(
            actions
        )

        actions_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        actions_layout.setSpacing(
            10
        )

        self.cancel_button = QPushButton(
            "Cancelar"
        )

        self.cancel_button.setFixedHeight(
            40
        )

        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: white;

                color: #475569;

                border: 1px solid #DBEAFE;
                border-radius: 10px;

                padding: 0px 16px;

                font-size: 14px;
            }

            QPushButton:hover {
                background-color: #F8FAFC;
            }
        """)

        self.draft_button = QPushButton(
            "Salvar rascunho"
        )

        self.draft_button.setFixedHeight(
            40
        )

        self.draft_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;

                color: #1D4ED8;

                border: none;

                padding: 0px 14px;

                font-size: 14px;
                font-weight: 500;
            }

            QPushButton:hover {
                color: #1E40AF;
            }
        """)

        self.save_button = QPushButton(
            "Cadastrar produto"
        )

        self.save_button.setIcon(
            qta.icon(
                "fa5s.check",
                color="white"
            )
        )

        self.save_button.setIconSize(
            QSize(13, 13)
        )

        self.save_button.setFixedHeight(
            40
        )

        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;

                color: white;

                border: none;
                border-radius: 10px;

                padding: 0px 18px;

                font-size: 14px;
                font-weight: 500;
            }

            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)

        actions_layout.addWidget(
            self.cancel_button
        )

        actions_layout.addWidget(
            self.draft_button
        )

        actions_layout.addWidget(
            self.save_button
        )

        layout.addWidget(
            left,
            1
        )

        layout.addWidget(
            actions,
            0,
            Qt.AlignTop
        )

        return header

    # ======================================================
    # CARD INFORMAÇÕES BÁSICAS
    # ======================================================

    def _create_basic_info_card(self):

        card = QFrame()

        card.setObjectName(
            "basicInfoCard"
        )

        card.setStyleSheet("""
            QFrame#basicInfoCard {
                background-color: #FFFFFF;

                border: 1px solid #DBEAFE;
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(
            card
        )

        layout.setContentsMargins(
            20,
            20,
            20,
            20
        )

        layout.setSpacing(
            16
        )

        layout.addLayout(
            self._create_card_header(
                "fa5s.box",
                "Informações básicas",
                "Dados de identificação e classificação do produto."
            )
        )

        layout.addWidget(
            self._create_divider()
        )

        # --------------------------------------------------
        # NOME
        # --------------------------------------------------

        name_container = self._create_field_container(
            "Nome do produto"
        )

        self.name_input = QLineEdit()

        self.name_input.setPlaceholderText(
            'Ex.: Monitor LG UltraWide 34"'
        )

        self._style_line_edit(
            self.name_input
        )

        name_container.layout().addWidget(
            self.name_input
        )

        layout.addWidget(
            name_container
        )

        # --------------------------------------------------
        # SKU + CATEGORIA
        # --------------------------------------------------

        row = QHBoxLayout()

        row.setSpacing(
            16
        )

        sku_container = self._create_field_container(
            "Código / SKU"
        )

        sku_wrapper = QFrame()

        sku_wrapper.setObjectName(
            "skuWrapper"
        )

        sku_wrapper.setFixedHeight(
            42
        )

        sku_wrapper.setStyleSheet("""
            QFrame#skuWrapper {
                background-color: #FFFFFF;

                border: 1px solid #CBD5E1;
                border-radius: 10px;
            }
        """)

        sku_layout = QHBoxLayout(
            sku_wrapper
        )

        sku_layout.setContentsMargins(
            12,
            0,
            12,
            0
        )

        sku_layout.setSpacing(
            8
        )

        self.code_input = QLineEdit()

        self.code_input.setText(
            "PRD-009"
        )

        self.code_input.setReadOnly(
            True
        )

        self.code_input.setStyleSheet("""
            QLineEdit {
                background-color: transparent;

                color: #334155;

                border: none;

                font-size: 14px;
            }
        """)

        automatic_label = QLabel(
            "Automático"
        )

        automatic_label.setStyleSheet("""
            color: #2563EB;

            font-size: 12px;
        """)

        sku_layout.addWidget(
            self.code_input,
            1
        )

        sku_layout.addWidget(
            automatic_label
        )

        sku_container.layout().addWidget(
            sku_wrapper
        )

        category_container = self._create_field_container(
            "Categoria"
        )

        self.category_input = QComboBox()

        self.category_input.addItems(
            [
                "Selecione uma categoria",
            ]
        )

        self._style_combo_box(
            self.category_input
        )

        category_container.layout().addWidget(
            self.category_input
        )

        row.addWidget(
            sku_container
        )

        row.addWidget(
            category_container
        )

        layout.addLayout(
            row
        )

        # --------------------------------------------------
        # DESCRIÇÃO
        # --------------------------------------------------

        description_container = QWidget()

        description_layout = QVBoxLayout(
            description_container
        )

        description_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        description_layout.setSpacing(
            6
        )

        label_row = QHBoxLayout()

        description_label = QLabel(
            "Descrição"
        )

        description_label.setStyleSheet("""
            color: #475569;

            font-size: 13px;
            font-weight: 500;
        """)

        optional_label = QLabel(
            "(opcional)"
        )

        optional_label.setStyleSheet("""
            color: #94A3B8;

            font-size: 12px;
        """)

        label_row.addWidget(
            description_label
        )

        label_row.addWidget(
            optional_label
        )

        label_row.addStretch()

        self.description_input = QTextEdit()

        self.description_input.setPlaceholderText(
            "Descreva as principais características do produto..."
        )

        self.description_input.setFixedHeight(
            100
        )

        self.description_input.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;

                color: #0F172A;

                border: 1px solid #CBD5E1;
                border-radius: 10px;

                padding: 10px;

                font-size: 14px;
            }

            QTextEdit:focus {
                border: 2px solid #93C5FD;
            }
        """)

        self.description_counter = QLabel(
            "0 / 500 caracteres"
        )

        self.description_counter.setAlignment(
            Qt.AlignRight
        )

        self.description_counter.setStyleSheet("""
            color: #94A3B8;

            font-size: 11px;
        """)

        description_layout.addLayout(
            label_row
        )

        description_layout.addWidget(
            self.description_input
        )

        description_layout.addWidget(
            self.description_counter
        )

        layout.addWidget(
            description_container
        )

        self.description_input.textChanged.connect(
            self._update_description_counter
        )

        return card

    # ======================================================
    # CARD PREÇO E TRIBUTAÇÃO
    # ======================================================

    def _create_price_tax_card(self):

        card = QFrame()

        card.setObjectName(
            "priceTaxCard"
        )

        card.setStyleSheet("""
            QFrame#priceTaxCard {
                background-color: #FFFFFF;

                border: 1px solid #DBEAFE;
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(
            card
        )

        layout.setContentsMargins(
            20,
            20,
            20,
            20
        )

        layout.setSpacing(
            16
        )

        layout.addLayout(
            self._create_card_header(
                "fa5s.dollar-sign",
                "Preço e tributação",
                "Defina os valores de custo, venda e dados fiscais."
            )
        )

        layout.addWidget(
            self._create_divider()
        )

        # ==================================================
        # PREÇO CUSTO + VENDA + UNIDADE
        # ==================================================

        first_row = QHBoxLayout()

        first_row.setSpacing(
            16
        )

        # Preço de custo
        cost_container = self._create_field_container(
            "Preço de custo"
        )

        self.cost_price_input = QDoubleSpinBox()

        self._configure_money_spinbox(
            self.cost_price_input
        )

        cost_container.layout().addWidget(
            self.cost_price_input
        )

        # Preço de venda
        sale_container = self._create_field_container(
            "Preço de venda"
        )

        self.sale_price_input = QDoubleSpinBox()

        self._configure_money_spinbox(
            self.sale_price_input
        )

        sale_container.layout().addWidget(
            self.sale_price_input
        )

        # Unidade
        unit_container = self._create_field_container(
            "Unidade"
        )

        self.unit_input = QComboBox()

        self.unit_input.addItems(
            [
                "Unidade (UN)",
                "Caixa (CX)",
                "Pacote (PCT)",
                "Quilograma (KG)",
                "Grama (G)",
                "Litro (L)",
                "Metro (M)",
            ]
        )

        self._style_combo_box(
            self.unit_input
        )

        unit_container.layout().addWidget(
            self.unit_input
        )

        first_row.addWidget(
            cost_container
        )

        first_row.addWidget(
            sale_container
        )

        first_row.addWidget(
            unit_container
        )

        layout.addLayout(
            first_row
        )

        # ==================================================
        # NCM + EAN
        # ==================================================

        second_row = QHBoxLayout()

        second_row.setSpacing(
            16
        )

        ncm_container = self._create_optional_field_container(
            "NCM"
        )

        self.ncm_input = QLineEdit()

        self.ncm_input.setPlaceholderText(
            "0000.00.00"
        )

        self._style_line_edit(
            self.ncm_input
        )

        ncm_container.layout().addWidget(
            self.ncm_input
        )

        ean_container = self._create_optional_field_container(
            "Código de barras / EAN"
        )

        self.ean_input = QLineEdit()

        self.ean_input.setPlaceholderText(
            "7890000000000"
        )

        self._style_line_edit(
            self.ean_input
        )

        ean_container.layout().addWidget(
            self.ean_input
        )

        second_row.addWidget(
            ncm_container
        )

        second_row.addWidget(
            ean_container
        )

        layout.addLayout(
            second_row
        )

        return card

    # ======================================================
    # CARD HEADER REUTILIZÁVEL
    # ======================================================

    def _create_card_header(
        self,
        icon_name,
        title_text,
        subtitle_text
    ):

        header_layout = QHBoxLayout()

        header_layout.setSpacing(
            12
        )

        icon_container = QFrame()

        icon_container.setFixedSize(
            38,
            38
        )

        icon_container.setStyleSheet("""
            background-color: #EFF6FF;

            border: none;
            border-radius: 10px;
        """)

        icon_layout = QVBoxLayout(
            icon_container
        )

        icon_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        icon = QLabel()

        icon.setAlignment(
            Qt.AlignCenter
        )

        icon.setPixmap(
            qta.icon(
                icon_name,
                color="#2563EB"
            ).pixmap(
                16,
                16
            )
        )

        icon_layout.addWidget(
            icon
        )

        text_container = QWidget()

        text_layout = QVBoxLayout(
            text_container
        )

        text_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        text_layout.setSpacing(
            2
        )

        title = QLabel(
            title_text
        )

        title.setStyleSheet("""
            color: #0F172A;

            font-size: 16px;
            font-weight: 600;
        """)

        subtitle = QLabel(
            subtitle_text
        )

        subtitle.setStyleSheet("""
            color: #94A3B8;

            font-size: 12px;
        """)

        text_layout.addWidget(
            title
        )

        text_layout.addWidget(
            subtitle
        )

        header_layout.addWidget(
            icon_container
        )

        header_layout.addWidget(
            text_container
        )

        header_layout.addStretch()

        return header_layout

    # ======================================================
    # DIVISOR
    # ======================================================

    def _create_divider(self):

        divider = QFrame()

        divider.setFixedHeight(
            1
        )

        divider.setStyleSheet("""
            background-color: #EFF6FF;

            border: none;
        """)

        return divider

    # ======================================================
    # CONTADOR
    # ======================================================

    def _update_description_counter(self):

        text = self.description_input.toPlainText()

        if len(text) > 500:

            text = text[:500]

            self.description_input.blockSignals(
                True
            )

            self.description_input.setPlainText(
                text
            )

            cursor = self.description_input.textCursor()

            cursor.movePosition(
                QTextCursor.End
            )

            self.description_input.setTextCursor(
                cursor
            )

            self.description_input.blockSignals(
                False
            )

        self.description_counter.setText(
            f"{len(text)} / 500 caracteres"
        )

    # ======================================================
    # PLACEHOLDER DOS PRÓXIMOS CARDS
    # ======================================================

    def _placeholder_card(
        self,
        title
    ):

        card = QFrame()

        card.setMinimumHeight(
            160
        )

        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;

                border: 1px solid #DBEAFE;
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(
            card
        )

        layout.setContentsMargins(
            20,
            20,
            20,
            20
        )

        label = QLabel(
            title
        )

        label.setStyleSheet("""
            color: #0F172A;

            font-size: 16px;
            font-weight: 600;

            border: none;
        """)

        layout.addWidget(
            label
        )

        layout.addStretch()

        return card

    # ======================================================
    # FIELD CONTAINER
    # ======================================================

    def _create_field_container(
        self,
        label_text
    ):

        container = QWidget()

        layout = QVBoxLayout(
            container
        )

        layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        layout.setSpacing(
            6
        )

        label = QLabel(
            label_text
        )

        label.setStyleSheet("""
            color: #475569;

            font-size: 13px;
            font-weight: 500;
        """)

        layout.addWidget(
            label
        )

        return container

    # ======================================================
    # FIELD CONTAINER OPCIONAL
    # ======================================================

    def _create_optional_field_container(
        self,
        label_text
    ):

        container = QWidget()

        layout = QVBoxLayout(
            container
        )

        layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        layout.setSpacing(
            6
        )

        label_row = QHBoxLayout()

        label = QLabel(
            label_text
        )

        label.setStyleSheet("""
            color: #475569;

            font-size: 13px;
            font-weight: 500;
        """)

        optional = QLabel(
            "(opcional)"
        )

        optional.setStyleSheet("""
            color: #94A3B8;

            font-size: 12px;
        """)

        label_row.addWidget(
            label
        )

        label_row.addWidget(
            optional
        )

        label_row.addStretch()

        layout.addLayout(
            label_row
        )

        return container

    # ======================================================
    # ESTILO QLINEEDIT
    # ======================================================

    def _style_line_edit(
        self,
        widget
    ):

        widget.setFixedHeight(
            42
        )

        widget.setStyleSheet("""
            QLineEdit {
                background-color: #FFFFFF;

                color: #0F172A;

                border: 1px solid #CBD5E1;
                border-radius: 10px;

                padding: 0px 12px;

                font-size: 14px;
            }

            QLineEdit:focus {
                border: 2px solid #93C5FD;
            }
        """)

    # ======================================================
    # ESTILO COMBOBOX
    # ======================================================

    def _style_combo_box(
        self,
        widget
    ):

        widget.setFixedHeight(
            42
        )

        widget.setStyleSheet("""
            QComboBox {
                background-color: #FFFFFF;

                color: #334155;

                border: 1px solid #CBD5E1;
                border-radius: 10px;

                padding: 0px 12px;

                font-size: 14px;
            }

            QComboBox:focus {
                border: 2px solid #93C5FD;
            }

            QComboBox::drop-down {
                border: none;

                width: 30px;
            }
        """)

    # ======================================================
    # MONEY SPINBOX
    # ======================================================

    def _configure_money_spinbox(
        self,
        widget
    ):

        widget.setMinimum(
            0
        )

        widget.setMaximum(
            99999999
        )

        widget.setDecimals(
            2
        )

        widget.setSingleStep(
            1
        )

        widget.setPrefix(
            "R$ "
        )

        widget.setFixedHeight(
            42
        )

        widget.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #FFFFFF;

                color: #0F172A;

                border: 1px solid #CBD5E1;
                border-radius: 10px;

                padding: 0px 10px;

                font-size: 14px;
            }

            QDoubleSpinBox:focus {
                border: 2px solid #93C5FD;
            }

            QDoubleSpinBox::up-button,
            QDoubleSpinBox::down-button {
                width: 20px;

                border: none;

                background-color: transparent;
            }
        """)