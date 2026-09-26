import qtawesome as qta

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QTextEdit,
    QSpinBox,
    QDoubleSpinBox,
)

from PySide6.QtCore import Qt, QSize


class NovoProdutoPage(QWidget):

    def __init__(self):
        super().__init__()

        self.setObjectName("novoProdutoPage")

        self.setStyleSheet("""
            QWidget#novoProdutoPage {
                background-color: #F0F5FF;
            }
        """)

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            28,
            28,
            28,
            28
        )

        main_layout.setSpacing(20)


        # ==================================================
        # CABEÇALHO
        # ==================================================

        header_layout = QHBoxLayout()

        title_container = QWidget()

        title_layout = QVBoxLayout(title_container)

        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)


        title = QLabel("Novo Produto")

        title.setStyleSheet("""
            color: #0F172A;
            font-size: 28px;
            font-weight: 700;
        """)


        subtitle = QLabel(
            "Cadastre um novo produto no estoque."
        )

        subtitle.setStyleSheet("""
            color: #64748B;
            font-size: 14px;
        """)


        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)


        # Botão voltar
        self.back_button = QPushButton("Voltar")

        self.back_button.setIcon(
            qta.icon(
                "fa5s.arrow-left",
                color="#475569"
            )
        )

        self.back_button.setIconSize(
            QSize(14, 14)
        )

        self.back_button.setFixedHeight(40)

        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: #475569;

                border: 1px solid #DBEAFE;
                border-radius: 10px;

                padding: 0px 16px;

                font-size: 14px;
            }

            QPushButton:hover {
                background-color: #EFF6FF;
            }
        """)


        header_layout.addWidget(title_container)
        header_layout.addStretch()
        header_layout.addWidget(self.back_button)

        main_layout.addLayout(header_layout)


        # ==================================================
        # CARD DO FORMULÁRIO
        # ==================================================

        form_card = QFrame()

        form_card.setObjectName("formCard")

        form_card.setStyleSheet("""
            QFrame#formCard {
                background-color: white;

                border: 1px solid #DBEAFE;
                border-radius: 16px;
            }
        """)

        form_layout = QVBoxLayout(form_card)

        form_layout.setContentsMargins(
            28,
            28,
            28,
            28
        )

        form_layout.setSpacing(20)


        # ==================================================
        # SEÇÃO: INFORMAÇÕES BÁSICAS
        # ==================================================

        section_title = QLabel(
            "Informações do Produto"
        )

        section_title.setStyleSheet("""
            color: #0F172A;
            font-size: 17px;
            font-weight: 600;
            border: none;
        """)

        form_layout.addWidget(section_title)


        # --------------------------------------------------
        # LINHA 1
        # --------------------------------------------------

        row1 = QHBoxLayout()

        row1.setSpacing(16)


        # Nome
        name_container = self.create_field_container(
            "Nome do produto"
        )

        self.name_input = QLineEdit()

        self.name_input.setPlaceholderText(
            "Nome do produto"
        )

        self.style_line_edit(
            self.name_input
        )

        name_container.layout().addWidget(
            self.name_input
        )


        # Código
        code_container = self.create_field_container(
            "Código"
        )

        self.code_input = QLineEdit()

        self.code_input.setPlaceholderText(
            "Código do produto"
        )

        self.style_line_edit(
            self.code_input
        )

        code_container.layout().addWidget(
            self.code_input
        )


        row1.addWidget(
            name_container,
            2
        )

        row1.addWidget(
            code_container,
            1
        )

        form_layout.addLayout(row1)


        # --------------------------------------------------
        # LINHA 2
        # --------------------------------------------------

        row2 = QHBoxLayout()

        row2.setSpacing(16)


        # Categoria
        category_container = self.create_field_container(
            "Categoria"
        )

        self.category_input = QComboBox()

        self.category_input.addItems(
            [
                "Selecione uma categoria",
            ]
        )

        self.style_combo_box(
            self.category_input
        )

        category_container.layout().addWidget(
            self.category_input
        )


        # Preço
        price_container = self.create_field_container(
            "Preço"
        )

        self.price_input = QDoubleSpinBox()

        self.price_input.setMinimum(0)

        self.price_input.setMaximum(
            99999999
        )

        self.price_input.setDecimals(2)

        self.price_input.setPrefix(
            "R$ "
        )

        self.style_spin_box(
            self.price_input
        )

        price_container.layout().addWidget(
            self.price_input
        )


        row2.addWidget(
            category_container
        )

        row2.addWidget(
            price_container
        )

        form_layout.addLayout(row2)


        # ==================================================
        # SEÇÃO: ESTOQUE
        # ==================================================

        stock_title = QLabel(
            "Controle de Estoque"
        )

        stock_title.setStyleSheet("""
            color: #0F172A;
            font-size: 17px;
            font-weight: 600;
            border: none;
        """)

        form_layout.addWidget(
            stock_title
        )


        row3 = QHBoxLayout()

        row3.setSpacing(16)


        # Estoque atual
        current_stock_container = self.create_field_container(
            "Quantidade inicial"
        )

        self.current_stock_input = QSpinBox()

        self.current_stock_input.setMinimum(0)

        self.current_stock_input.setMaximum(
            999999
        )

        self.style_spin_box(
            self.current_stock_input
        )

        current_stock_container.layout().addWidget(
            self.current_stock_input
        )


        # Estoque mínimo
        minimum_stock_container = self.create_field_container(
            "Estoque mínimo"
        )

        self.minimum_stock_input = QSpinBox()

        self.minimum_stock_input.setMinimum(0)

        self.minimum_stock_input.setMaximum(
            999999
        )

        self.style_spin_box(
            self.minimum_stock_input
        )

        minimum_stock_container.layout().addWidget(
            self.minimum_stock_input
        )


        row3.addWidget(
            current_stock_container
        )

        row3.addWidget(
            minimum_stock_container
        )

        form_layout.addLayout(row3)


        # ==================================================
        # DESCRIÇÃO
        # ==================================================

        description_container = self.create_field_container(
            "Descrição"
        )

        self.description_input = QTextEdit()

        self.description_input.setPlaceholderText(
            "Adicione uma descrição para o produto..."
        )

        self.description_input.setFixedHeight(
            120
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

        description_container.layout().addWidget(
            self.description_input
        )

        form_layout.addWidget(
            description_container
        )


        # ==================================================
        # BOTÕES
        # ==================================================

        actions_layout = QHBoxLayout()

        actions_layout.addStretch()


        self.cancel_button = QPushButton(
            "Cancelar"
        )

        self.cancel_button.setFixedHeight(
            42
        )

        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: #475569;

                border: 1px solid #CBD5E1;
                border-radius: 10px;

                padding: 0px 18px;

                font-size: 14px;
            }

            QPushButton:hover {
                background-color: #F8FAFC;
            }
        """)


        self.save_button = QPushButton(
            "Cadastrar Produto"
        )

        self.save_button.setIcon(
            qta.icon(
                "fa5s.save",
                color="white"
            )
        )

        self.save_button.setIconSize(
            QSize(14, 14)
        )

        self.save_button.setFixedHeight(
            42
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
            self.save_button
        )

        form_layout.addLayout(
            actions_layout
        )


        main_layout.addWidget(
            form_card
        )

        main_layout.addStretch()


    # ======================================================
    # HELPERS
    # ======================================================

    def create_field_container(
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

        layout.setSpacing(6)


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


    def style_line_edit(
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


    def style_combo_box(
        self,
        widget
    ):

        widget.setFixedHeight(
            42
        )

        widget.setStyleSheet("""
            QComboBox {
                background-color: #FFFFFF;
                color: #0F172A;

                border: 1px solid #CBD5E1;
                border-radius: 10px;

                padding: 0px 12px;

                font-size: 14px;
            }

            QComboBox:focus {
                border: 2px solid #93C5FD;
            }
        """)


    def style_spin_box(
        self,
        widget
    ):

        widget.setFixedHeight(
            42
        )

        widget.setStyleSheet("""
            QSpinBox,
            QDoubleSpinBox {
                background-color: #FFFFFF;
                color: #0F172A;

                border: 1px solid #CBD5E1;
                border-radius: 10px;

                padding: 0px 12px;

                font-size: 14px;
            }

            QSpinBox:focus,
            QDoubleSpinBox:focus {
                border: 2px solid #93C5FD;
            }
        """)