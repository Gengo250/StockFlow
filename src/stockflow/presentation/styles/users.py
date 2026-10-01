USERS_QSS = """
    QWidget#usersPage, QDialog#userForm { background: #F0F5FF; }
    QWidget#usersPage QLabel, QDialog#userForm QLabel {
        background: transparent; color: #263650; font-size: 13px;
    }
    QWidget#usersPage QLabel#pageTitle, QDialog#userForm QLabel#pageTitle {
        color: #0F172A; font-size: 24px; font-weight: 700;
    }
    QWidget#usersPage QLabel#muted, QDialog#userForm QLabel#muted {
        color: #6980A5; font-size: 12px;
    }
    QFrame#summaryCard, QFrame#userTableCard {
        background: white; border: 1px solid #D7E5FF; border-radius: 14px;
    }
    QLineEdit, QComboBox {
        background: white; color: #475569; border: 1px solid #D7E5FF;
        border-radius: 10px; padding: 10px 12px; font-size: 13px;
    }
    QLineEdit:focus, QComboBox:focus { border: 1px solid #195BFF; }
    QComboBox::drop-down { border: none; width: 24px; }
    QComboBox QAbstractItemView { background: white; color: #263650; selection-background-color: #DBEAFE; }
    QPushButton { padding: 10px 14px; border-radius: 10px; font-size: 13px; }
    QPushButton#primaryButton, QPushButton:checked {
        background: #195BFF; color: white; border: 1px solid #195BFF;
    }
    QPushButton#primaryButton:hover { background: #154EDD; }
    QPushButton#secondaryButton {
        background: white; color: #475569; border: 1px solid #D7E5FF;
    }
    QPushButton#secondaryButton:checked { background: #195BFF; color: white; }
    QPushButton#secondaryButton:hover { border-color: #90B5FF; }
    QPushButton#primaryButton:disabled { background: #90B5FF; border-color: #90B5FF; }
    QPushButton#secondaryButton:disabled { color: #8A9DBA; }
    QPushButton#iconButton { background: transparent; border: none; padding: 4px; }
    QPushButton#iconButton:hover { background: #EAF1FF; }
    QTableWidget { background: white; color: #6980A5; border: none; font-size: 12px; }
    QTableWidget::item { padding: 10px; border-bottom: 1px solid #EDF3FF; }
    QTableWidget::item:selected { background: #E7EFFF; color: #243F70; }
    QHeaderView::section {
        background: #F4F8FF; color: #60799E; border: none;
        border-bottom: 1px solid #D7E5FF; padding: 13px 12px; font-size: 11px;
    }
"""
