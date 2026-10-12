SETTINGS_QSS = """
    QWidget#settingsPage, QWidget#settingsContent, QScrollArea {
        background: #F0F5FF; border: none;
    }
    QLabel { color: #0F172A; font-size: 14px; background: transparent; }
    QLabel#settingsTitle { font-size: 28px; font-weight: 700; }
    QLabel#settingsSubtitle { color: #64748B; font-size: 13px; }
    QLabel#settingsNotice {
        background: #E8F0FF; color: #1E40AF; border: 1px solid #C7DBFF;
        border-radius: 10px; padding: 14px; font-size: 13px;
    }
    QCheckBox {
        color: #0F172A; font-size: 14px; font-weight: 500;
        background: transparent; spacing: 10px; padding: 3px;
    }
    QCheckBox:focus { outline: 1px solid #2563EB; }
    QPushButton {
        background: white; color: #2563EB; border: 1px solid #BFDBFE;
        border-radius: 10px; padding: 12px 16px; font-size: 13px;
    }
    QPushButton:hover { background: #EFF6FF; border-color: #93C5FD; }
    QPushButton:focus { border: 2px solid #2563EB; }
    QScrollBar:vertical { background: transparent; width: 8px; }
    QScrollBar::handle:vertical {
        background: #CBD5E1; border-radius: 4px; min-height: 30px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""
