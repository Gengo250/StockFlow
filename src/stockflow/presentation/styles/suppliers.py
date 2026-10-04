SUPPLIERS_QSS = """
    QWidget#suppliersPage { background: #F0F5FF; }
    QWidget#suppliersPage QLabel { background: transparent; color: #263650; font-size: 13px; }
    QWidget#suppliersPage QLabel#pageTitle { color: #0F172A; font-size: 24px; font-weight: 700; }
    QWidget#suppliersPage QLabel#muted { color: #6980A5; font-size: 12px; }
    QDialog#supplierForm { background: #F0F5FF; }
    QDialog#supplierForm QLabel { background: transparent; color: #263650; font-size: 13px; }
    QFrame#suppliersTableCard { background: white; border: 1px solid #D7E5FF; border-radius: 14px; }
    QLineEdit, QComboBox { background: white; color: #475569; border: 1px solid #D7E5FF; border-radius: 10px; padding: 10px 12px; font-size: 13px; }
    QLineEdit:focus, QComboBox:focus { border: 1px solid #195BFF; }
    QPushButton { padding: 10px 14px; border-radius: 10px; font-size: 13px; }
    QPushButton#primaryButton { background: #195BFF; color: white; border: 1px solid #195BFF; }
    QPushButton#primaryButton:hover { background: #154EDD; }
    QPushButton#secondaryButton { background: white; color: #475569; border: 1px solid #D7E5FF; }
    QPushButton#secondaryButton:hover { background: #F3F8FF; border-color: #90B5FF; }
    QPushButton#supplierActionButton {
        background: white; color: #475569; border: 1px solid #D7E5FF;
        border-radius: 8px; padding: 5px 8px; font-size: 12px;
    }
    QPushButton#supplierActionButton:hover { background: #F3F8FF; border-color: #90B5FF; }
    QTableWidget { background: white; color: #6980A5; border: none; font-size: 12px; }
    QTableWidget::item { padding: 10px; border-bottom: 1px solid #EDF3FF; }
    QTableWidget::item:selected { background: #E7EFFF; color: #243F70; }
    QHeaderView::section { background: #F4F8FF; color: #60799E; border: none; border-bottom: 1px solid #D7E5FF; padding: 13px 12px; font-size: 11px; }
    QLabel#statusBadge { border-radius: 999px; padding: 6px 10px; font-weight: 600; color: #0F172A; }
    QLabel#statusBadge[status="Ativo"] { background: #E4F7EF; color: #0F7B4F; }
    QLabel#statusBadge[status="Inativo"] { background: #FBE9E9; color: #8A3B3B; }
"""
