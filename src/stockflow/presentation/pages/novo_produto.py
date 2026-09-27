import qtawesome as qta

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from stockflow.presentation.widgets.product_form import (
    BasicInfoCard,
    BeforeRegisterCard,
    PriceTaxCard,
    ProductImageCard,
    ProductStatusCard,
    StockControlCard,
)


class NovoProdutoPage(QWidget):
    def __init__(self, edit_mode=False):
        super().__init__()
        self.edit_mode = edit_mode
        self.setObjectName("novoProdutoPage")
        self.setStyleSheet("""
            QWidget#novoProdutoPage { background-color: #F0F5FF; }
            QWidget#novoProdutoPage QLabel { background-color: transparent; }
        """)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background-color: #F0F5FF; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 2px; }
            QScrollBar::handle:vertical {
                background: #CBD5E1;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #94A3B8; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        content = QWidget()
        content.setObjectName("novoProdutoContent")
        content.setMaximumWidth(1600)
        content.setStyleSheet("""
            QWidget#novoProdutoContent { background-color: #F0F5FF; }
            QWidget#novoProdutoContent QLabel { background-color: transparent; }
        """)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 24, 26, 36)
        content_layout.setSpacing(24)
        content_layout.addWidget(self._create_header())
        content_layout.addLayout(self._create_columns())

        scroll_container = QWidget()
        scroll_container.setObjectName("novoProdutoScrollContainer")
        scroll_container.setStyleSheet("""
            QWidget#novoProdutoScrollContainer { background-color: #F0F5FF; }
        """)
        scroll_layout = QHBoxLayout(scroll_container)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addStretch()
        scroll_layout.addWidget(content)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_container)
        page_layout.addWidget(scroll)

    def _create_columns(self):
        columns = QHBoxLayout()
        columns.setSpacing(22)
        columns.setContentsMargins(0, 0, 0, 0)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(20)
        self.basic_info_card = BasicInfoCard()
        self.price_tax_card = PriceTaxCard()
        self.stock_control_card = StockControlCard()
        left_layout.addWidget(self.basic_info_card)
        left_layout.addWidget(self.price_tax_card)
        left_layout.addWidget(self.stock_control_card)
        left_layout.addStretch()

        right = QWidget()
        right.setMaximumWidth(430)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(20)
        self.image_card = ProductImageCard()
        self.status_card = ProductStatusCard()
        self.before_register_card = BeforeRegisterCard()
        right_layout.addWidget(self.image_card)
        right_layout.addWidget(self.status_card)
        right_layout.addWidget(self.before_register_card)
        right_layout.addStretch()

        columns.addWidget(left, 7)
        columns.addWidget(right, 3)
        self._expose_form_fields()
        return columns

    def _expose_form_fields(self):
        groups = (
            (self.basic_info_card, (
                "name_input", "code_input", "category_input", "description_input", "description_counter",
            )),
            (self.price_tax_card, (
                "cost_price_input", "sale_price_input", "unit_input", "ncm_input", "ean_input",
            )),
            (self.stock_control_card, (
                "initial_stock_input", "minimum_stock_input", "location_input", "supplier_input", "low_stock_alert",
            )),
            (self.status_card, ("product_status_toggle", "status_dot", "status_label")),
        )
        for widget, names in groups:
            for name in names:
                setattr(self, name, getattr(widget, name))

    def _create_header(self):
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        self.back_button = QPushButton("Produtos")
        self.back_button.setIcon(qta.icon("fa5s.chevron-left", color="#64748B"))
        self.back_button.setIconSize(QSize(10, 10))
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #64748B;
                border: none;
                text-align: left;
                padding: 0px;
                font-size: 13px;
            }
            QPushButton:hover { color: #2563EB; }
        """)
        title = QLabel("Editar produto" if self.edit_mode else "Cadastrar novo produto")
        title.setStyleSheet("""
            background-color: transparent;
            color: #0F172A;
            font-size: 28px;
            font-weight: 700;
        """)
        subtitle = QLabel(
            "Atualize as informações comerciais e de estoque do item."
            if self.edit_mode
            else "Adicione as informações comerciais e de estoque do item."
        )
        subtitle.setStyleSheet("background-color: transparent; color: #64748B; font-size: 14px;")
        left_layout.addWidget(self.back_button, alignment=Qt.AlignLeft)
        left_layout.addSpacing(6)
        left_layout.addWidget(title)
        left_layout.addWidget(subtitle)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        self.cancel_button = self._action_button("Cancelar", """
            QPushButton {
                background-color: #FFFFFF;
                color: #475569;
                border: 1px solid #DBEAFE;
                border-radius: 10px;
                padding: 0px 16px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #F8FAFC; }
        """)
        self.draft_button = self._action_button("Salvar rascunho", """
            QPushButton {
                background-color: transparent;
                color: #1D4ED8;
                border: none;
                padding: 0px 14px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover { color: #1E40AF; }
        """)
        self.draft_button.setVisible(not self.edit_mode)
        self.save_button = self._action_button(
            "Salvar alterações" if self.edit_mode else "Cadastrar produto",
            """
            QPushButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 0px 18px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """,
        )
        self.save_button.setIcon(qta.icon("fa5s.check", color="white"))
        self.save_button.setIconSize(QSize(13, 13))
        actions_layout.addWidget(self.cancel_button)
        actions_layout.addWidget(self.draft_button)
        actions_layout.addWidget(self.save_button)
        layout.addWidget(left, 1)
        layout.addWidget(actions, 0, Qt.AlignTop)
        return header

    @staticmethod
    def _action_button(text, style):
        button = QPushButton(text)
        button.setFixedHeight(40)
        button.setStyleSheet(style)
        return button

    def load_product(self, product):
        code, name, category, stock, price, status = product
        self.code_input.setText(code)
        self.name_input.setText(name)
        if self.category_input.findText(category) < 0:
            self.category_input.addItem(category)
        self.category_input.setCurrentText(category)
        self.initial_stock_input.setValue(int(stock))
        self.sale_price_input.setValue(
            float(price.removeprefix("R$ ").replace(".", "").replace(",", "."))
        )
        self.product_status_toggle.setChecked(status != "Inativo")
