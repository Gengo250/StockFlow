from .design_system import (
    LOAD_ERROR_QSS, button_qss, field_qss, page_qss, qss, surface_qss,
)

PRODUCTS_QSS = (page_qss("productsPage", "productDetailsPage", "movementDetailsPage")
    + button_qss() + button_qss("QPushButton#newProductButton", primary=True)
    + field_qss("QLineEdit") + surface_qss("QFrame#detailsCard") + qss("""
    QPushButton#newProductButton { min-height: 38px; }
    QLineEdit { min-height: 38px; }
    QPushButton#productCard {
        background: $SURFACE; border: 1px solid $BORDER; border-radius: 12px;
        padding: 0; text-align: left;
    }
    QPushButton#productCard:hover { background: $SURFACE; border-color: #93C5FD; }
    QPushButton#productCard:focus { border: 1px solid $PRIMARY; }
    QLabel#productCode { color: $MUTED; font-size: 11px; }
    QLabel#productName { color: $TEXT; font-size: 14px; font-weight: 600; }
    QLabel#productCategory {
        color: #475569; background: #F1F5F9; border-radius: 5px;
        padding: 3px 8px; font-size: 11px;
    }
    QLabel#productCaption { color: $MUTED; font-size: 12px; }
    QLabel#productPrice { color: $TEXT; font-size: 16px; font-weight: 700; }
    QFrame#productDivider { background: $BORDER; border: none; }
    QLabel#detailValue { color: $TEXT; font-size: 15px; font-weight: 500; }
    QScrollArea > QWidget > QWidget { background: $BACKGROUND; }
""") + "QLabel#loadError {" + LOAD_ERROR_QSS + "}")
