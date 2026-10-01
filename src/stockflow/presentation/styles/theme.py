"""Estilos da janela principal, barra superior e menu lateral."""

MAIN_WINDOW_QSS = """
    QMainWindow {
        background-color: #F0F5FF;
    }
"""


TOP_BAR_QSS = """
    QFrame#topBar {
        background-color: #FFFFFF;
        border: none;
        border-bottom: 1px solid #E5ECF7;
    }

    QLineEdit#quickSearch {
        background-color: #F0F6FF;
        color: #425B80;
        placeholder-text-color: #8BA1BF;
        border: 1px solid transparent;
        border-radius: 12px;
        padding: 0 8px;
        font-size: 13px;
        selection-background-color: #3482FF;
        selection-color: white;
    }

    QLineEdit#quickSearch:focus {
        border-color: #8BB9FF;
    }

    QToolButton#notificationsButton {
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 8px;
    }

    QToolButton#notificationsButton:hover {
        background-color: #F0F6FF;
    }

    QToolButton#notificationsButton:focus {
        border-color: #8BB9FF;
    }

    QLabel#topBarAvatar {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #4B9AFF, stop:1 #2164F5);
        color: white;
        border-radius: 10px;
        font-size: 12px;
        font-weight: 500;
    }
"""

CENTRAL_WIDGET_QSS = """
    QWidget#centralWidget {
        background-color: #F0F5FF;
    }
"""

PAGES_QSS = """
    QStackedWidget#pages {
        background-color: #F0F5FF;
    }
"""

DASHBOARD_PAGE_QSS = """
    background-color: #F0F5FF;
"""

SIDEBAR_QSS = """
    QFrame {
        background-color: #0E2971;
    }

    QLabel {
        background-color: transparent;
        color: white;
    }

    QPushButton {
        background-color: transparent;
        color: #D7E4FF;

        border: none;
        border-radius: 10px;

        text-align: left;

        padding: 10px 12px;

        font-size: 15px;
    }

    QPushButton:hover {
        background-color: #24479B;
    }

    QPushButton#activeButton {
        background-color: #4566B1;
        color: white;
        font-weight: 600;
    }
"""

DIVIDER_QSS = """
    background-color: #29458C;
"""

LOGO_ICON_QSS = """
    background-color: #365BB3;
    border-radius: 10px;
"""

APP_NAME_QSS = """
    color: white;
    font-size: 15px;
    font-weight: 500;
"""

APP_SUBTITLE_QSS = """
    color: #9DB7E8;
    font-size: 11px;
"""

SECTION_TITLE_QSS = """
    color: #5EAEF7;
    font-size: 12px;
    font-weight: 600;
    padding-left: 12px;
"""

AVATAR_QSS = """
    background-color: #3482FF;
    color: white;

    border-radius: 10px;

    font-size: 14px;
"""

USER_NAME_QSS = """
    color: white;
    font-size: 14px;
    font-weight: 600;
"""

USER_ROLE_QSS = """
    color: #9DB7E8;
    font-size: 11px;
"""

LOGOUT_BUTTON_QSS = """
    QPushButton {
        background-color: transparent;
        border: none;
    }

    QPushButton:hover {
        background-color: #24479B;
        border-radius: 8px;
    }
"""
