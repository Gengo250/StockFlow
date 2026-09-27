import qtawesome as qta

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)

from PySide6.QtCore import Qt, QSize, Signal


class EstoquePage(QWidget):

    product_edit_requested = Signal(object)

    def __init__(self):
        super().__init__()

        self.setObjectName("estoquePage")

        self.setStyleSheet("""
    QWidget#estoquePage {
        background-color: #F0F5FF;
    }
""")

        # ==================================================
        # PRODUTOS CARREGADOS
        # ==================================================

        self.produtos = [
            ("PRD-009", "Monitor LG UltraWide 34\"", "Eletrônicos", "18", "R$ 2.499,90", "Normal"),
            ("PRD-008", "Teclado mecânico sem fio", "Periféricos", "6", "R$ 459,90", "Baixo"),
            ("PRD-007", "Mouse ergonômico", "Periféricos", "2", "R$ 189,90", "Crítico"),
        ]


        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            22,
            22,
            22,
            22
        )

        main_layout.setSpacing(18)


        # ==================================================
        # CABEÇALHO
        # ==================================================

        header_layout = QHBoxLayout()

        title_container = QWidget()

        title_layout = QVBoxLayout(title_container)

        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)


        title = QLabel("Controle de Estoque")

        title.setStyleSheet("""
            color: #0F172A;
            font-size: 26px;
            font-weight: 700;
        """)


        subtitle = QLabel(
            f"{len(self.produtos)} produtos cadastrados"
        )

        subtitle.setStyleSheet("""
            color: #64748B;
            font-size: 14px;
        """)


        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)


        self.new_product_button = QPushButton("Novo Produto")

        self.new_product_button.setIcon(
            qta.icon(
                "fa5s.plus",
                color="white"
            )
        )

        self.new_product_button.setIconSize(QSize(14, 14))

        self.new_product_button.setFixedHeight(40)

        self.new_product_button.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;

                border: none;
                border-radius: 12px;

                padding: 0px 18px;

                font-size: 14px;
                font-weight: 500;
            }

            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)


        header_layout.addWidget(title_container)

        header_layout.addStretch()

        header_layout.addWidget(self.new_product_button)


        main_layout.addLayout(header_layout)


        # ==================================================
        # BUSCA + FILTROS
        # ==================================================

        filter_layout = QHBoxLayout()

        filter_layout.setSpacing(10)


        search_input = QLineEdit()

        search_input.setPlaceholderText(
            "Buscar produto ou código..."
        )

        search_input.setFixedHeight(44)

        search_input.addAction(
            qta.icon(
                "fa5s.search",
                color="#94A3B8"
            ),
            QLineEdit.LeadingPosition
        )

        search_input.setStyleSheet("""
            QLineEdit {
                background-color: white;

                border: 1px solid #BFDBFE;
                border-radius: 12px;

                padding: 0px 12px;

                color: #0F172A;

                font-size: 14px;
            }

            QLineEdit:focus {
                border: 2px solid #93C5FD;
            }
        """)


        filter_layout.addWidget(search_input, 1)


        # ==================================================
        # BOTÕES DE FILTRO
        # ==================================================

        self.filter_buttons = []

        filtros = [
            "Todos",
            "Normal",
            "Baixo",
            "Crítico"
        ]

        for index, texto in enumerate(filtros):

            button = QPushButton(texto)

            button.setCheckable(True)

            button.setFixedHeight(44)

            button.setMinimumWidth(82)

            button.setStyleSheet("""
                QPushButton {
                    background-color: white;
                    color: #475569;

                    border: 1px solid #DBEAFE;
                    border-radius: 12px;

                    padding: 0px 16px;

                    font-size: 14px;
                }

                QPushButton:hover {
                    border: 1px solid #93C5FD;
                }

                QPushButton:checked {
                    background-color: #2563EB;
                    color: white;

                    border: none;
                }
            """)

            if index == 0:
                button.setChecked(True)

            button.clicked.connect(
                lambda checked, btn=button:
                self.select_filter(btn)
            )

            self.filter_buttons.append(button)

            filter_layout.addWidget(button)


        main_layout.addLayout(filter_layout)


        # ==================================================
        # CONTAINER DA TABELA
        # ==================================================

        table_container = QFrame()

        table_container.setStyleSheet("""
            QFrame {
                background-color: white;

                border: 1px solid #DBEAFE;
                border-radius: 16px;
            }
        """)

        table_layout = QVBoxLayout(table_container)

        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)


        # ==================================================
        # TABELA
        # ==================================================

        self.table = QTableWidget()

        self.table.setColumnCount(7)

        self.table.setHorizontalHeaderLabels(
            [
                "Código",
                "Produto",
                "Categoria",
                "Estoque",
                "Preço",
                "Status",
                "Ações",
            ]
        )

        self.table.setRowCount(len(self.produtos))

        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )

        self.table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )

        self.table.verticalHeader().setVisible(False)

        self.table.setShowGrid(False)

        self.table.setAlternatingRowColors(False)

        self.table.setFocusPolicy(Qt.NoFocus)

        self.table.setStyleSheet("""
    QTableWidget {
        background-color: #FFFFFF;
        color: #0F172A;

        border: none;

        font-size: 14px;
    }

    QTableWidget::viewport {
        background-color: #FFFFFF;
    }

    QTableWidget::item {
        background-color: #FFFFFF;

        border-bottom: 1px solid #EFF6FF;

        padding: 8px;
    }

    QTableWidget::item:selected {
        background-color: #EFF6FF;
        color: #0F172A;
    }

    QHeaderView::section {
        background-color: #F8FBFF;
        color: #64748B;

        border: none;
        border-bottom: 1px solid #DBEAFE;

        padding: 10px;

        font-size: 12px;
        font-weight: 600;
    }
""")


        # ==================================================
        # TAMANHO DAS COLUNAS
        # ==================================================

        header = self.table.horizontalHeader()

        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents
        )

        header.setSectionResizeMode(
            1,
            QHeaderView.Stretch
        )

        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents
        )

        header.setSectionResizeMode(
            3,
            QHeaderView.ResizeToContents
        )

        header.setSectionResizeMode(
            4,
            QHeaderView.ResizeToContents
        )

        header.setSectionResizeMode(
            5,
            QHeaderView.ResizeToContents
        )

        header.setSectionResizeMode(
            6,
            QHeaderView.ResizeToContents
        )


        # ==================================================
        # PREENCHE A TABELA
        # ==================================================

        for row, produto in enumerate(self.produtos):

            codigo = QTableWidgetItem(
                produto[0]
            )

            codigo.setForeground(
                Qt.blue
            )

            self.table.setItem(
                row,
                0,
                codigo
            )


            self.table.setItem(
                row,
                1,
                QTableWidgetItem(produto[1])
            )


            self.table.setItem(
                row,
                2,
                QTableWidgetItem(produto[2])
            )


            self.table.setItem(
                row,
                3,
                QTableWidgetItem(produto[3])
            )


            self.table.setItem(
                row,
                4,
                QTableWidgetItem(produto[4])
            )


            self.table.setItem(
                row,
                5,
                QTableWidgetItem(produto[5])
            )


            # ==================================================
            # BOTÕES DE AÇÃO
            # ==================================================

            actions_widget = QWidget()

            actions_layout = QHBoxLayout(actions_widget)

            actions_layout.setContentsMargins(
                0,
                0,
                0,
                0
            )

            actions_layout.setSpacing(6)


            edit_button = QPushButton()

            edit_button.setIcon(
                qta.icon(
                    "fa5s.pen",
                    color="#94A3B8"
                )
            )

            edit_button.setFixedSize(28, 28)

            edit_button.setToolTip("Editar produto")

            edit_button.clicked.connect(
                lambda checked=False, item=produto:
                self.product_edit_requested.emit(item)
            )

            edit_button.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                }

                QPushButton:hover {
                    background-color: #EFF6FF;
                    border-radius: 6px;
                }
            """)


            delete_button = QPushButton()

            delete_button.setIcon(
                qta.icon(
                    "fa5s.trash-alt",
                    color="#94A3B8"
                )
            )

            delete_button.setFixedSize(28, 28)

            delete_button.setToolTip("Excluir produto")

            delete_button.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                }

                QPushButton:hover {
                    background-color: #FEF2F2;
                    border-radius: 6px;
                }
            """)


            actions_layout.addWidget(
                edit_button
            )

            actions_layout.addWidget(
                delete_button
            )


            self.table.setCellWidget(
                row,
                6,
                actions_widget
            )


        # ==================================================
        # ALTURA DAS LINHAS
        # ==================================================

        self.table.verticalHeader().setDefaultSectionSize(62)


        table_layout.addWidget(self.table)

        main_layout.addWidget(table_container)


    # ======================================================
    # FILTRO VISUAL
    # ======================================================

    def select_filter(self, selected_button):

        for button in self.filter_buttons:
            button.setChecked(
                button == selected_button
            )
