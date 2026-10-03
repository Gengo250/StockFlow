PAGE_QSS = """
    QWidget#estoquePage {
        background-color: #F0F5FF;
    }
"""

TITLE_QSS = """
            color: #0F172A;
            font-size: 26px;
            font-weight: 700;
        """

SUBTITLE_QSS = """
            color: #64748B;
            font-size: 14px;
        """

NEW_BUTTON_QSS = """
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
        """

SEARCH_QSS = """
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
        """

FILTER_QSS = """
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
            """

TABLE_CARD_QSS = """
            QFrame {
                background-color: white;

                border: 1px solid #DBEAFE;
                border-radius: 16px;
            }
        """

TABLE_QSS = """
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
"""
