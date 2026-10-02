PRODUCTS_QSS = """
    QPushButton#productCard {
        background: white; border: 1px solid #D7E6FF; border-radius: 16px;
        padding: 0; text-align: left;
    }
    QPushButton#productCard:hover { background: #FBFDFF; border-color: #93B8FF; }
    QPushButton#productCard:focus { border: 2px solid #2563EB; }
    QLabel#productCode { color: #3482FF; font-size: 11px; font-family: monospace; }
    QLabel#productName { color: #0F172A; font-size: 13px; font-weight: 600; }
    QLabel#productCategory {
        color: #195BFF; background: #EFF6FF; border-radius: 8px;
        padding: 2px 8px; font-size: 11px;
    }
    QLabel#productCaption { color: #8198B9; font-size: 11px; }
    QLabel#productPrice { color: #0F172A; font-size: 13px; font-weight: 700; font-family: monospace; }
    QFrame#productDivider { background: #EFF4FF; border: none; }
    QPushButton#newProductButton {
        background: #195BFF; color: white; border: none; border-radius: 12px;
        padding: 12px 16px;
    }
    QPushButton#newProductButton:hover { background: #1D4ED8; }
    QWidget#productsPage, QWidget#productDetailsPage {
        background: #F0F5FF;
    }
    QLabel { color: #0F172A; font-size: 14px; background: transparent; }
    QLabel#pageTitle { font-size: 28px; font-weight: 700; }
    QLabel#muted { color: #64748B; }
    QLabel#detailValue { font-size: 16px; font-weight: 500; }
    QFrame#detailsCard {
        background: white; border: 1px solid #DBEAFE; border-radius: 16px;
    }
    QScrollArea, QScrollArea > QWidget > QWidget { background: #F0F5FF; }
    QPushButton {
        background: #FFFFFF; color: #2563EB; border: 1px solid #DBEAFE;
        border-radius: 10px; padding: 10px 16px; font-size: 13px;
    }
    QPushButton:hover { background: #EFF6FF; border-color: #93C5FD; }
    QPushButton:focus { border: 2px solid #2563EB; }
    QLineEdit {
        background: white; color: #0F172A; border: 1px solid #BFDBFE;
        border-radius: 12px; padding: 12px; font-size: 14px;
        selection-background-color: #2563EB; selection-color: white;
    }
    QLineEdit:focus { border-color: #2563EB; }
    QLabel#loadError {
        background: #FFF7ED; color: #9A3412; border: 1px solid #FED7AA;
        border-radius: 12px; padding: 20px;
    }
"""
