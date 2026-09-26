"""Folhas de estilo da janela principal e da sidebar.

As strings são cópias literais do que estava inline em app/main.py
antes desta refatoração (ver histórico do git).
O QSS das páginas continua dentro de cada página.
"""

MAIN_WINDOW_QSS = """
    QMainWindow {
        background-color: #F0F5FF;
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
