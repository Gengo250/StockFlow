"""Application shell: navy navigation and a neutral work area."""
from .design_system import qss, SCROLL_QSS

MAIN_WINDOW_QSS = qss("QMainWindow { background: $BACKGROUND; }")
CENTRAL_WIDGET_QSS = qss("QWidget#centralWidget { background: $BACKGROUND; }")
PAGES_QSS = qss("QStackedWidget#pages { background: $BACKGROUND; }") + SCROLL_QSS
DASHBOARD_PAGE_QSS = qss("background: $BACKGROUND;")
TOP_BAR_QSS = qss("""
    QFrame#topBar { background: $SURFACE; border: none; border-bottom: 1px solid $BORDER; }
    QLabel#workspaceLabel { color: $MUTED; background: transparent; font-size: 12px; }
    QLineEdit#quickSearch {
        background: #F8FAFC; color: #475569; placeholder-text-color: $SUBTLE;
        border: 1px solid $BORDER; border-radius: 8px; padding: 0 10px;
        font-size: 12px; selection-background-color: $PRIMARY; selection-color: white;
    }
    QLineEdit#quickSearch:focus { border-color: $PRIMARY; }
    QToolButton#notificationsButton { background: transparent; border: 1px solid transparent; border-radius: 6px; }
    QToolButton#notificationsButton:hover { background: #F1F5F9; }
    QToolButton#notificationsButton:focus { border-color: $PRIMARY; }
    QLabel#topBarAvatar { background: $PRIMARY; color: white; border-radius: 8px; font-size: 12px; font-weight: 600; }
""")
SIDEBAR_QSS = qss("""
    QFrame { background: $NAVY; border: none; }
    QLabel { background: transparent; color: white; }
    QPushButton {
        background: transparent; color: #CCD8F4; border: 1px solid transparent;
        border-radius: 8px; text-align: left; padding: 8px 12px;
        font-size: 13px; font-weight: 500;
    }
    QPushButton:hover { background: #1B3877; color: white; }
    QPushButton:focus { border-color: #6C91E0; }
    QPushButton#activeButton { background: #284783; color: white; font-weight: 600; }
""")
DIVIDER_QSS = "background: #284174; border: none;"
LOGO_ICON_QSS = "background: #284C9C; border-radius: 10px;"
APP_NAME_QSS = "color: white; background: transparent; font-size: 18px; font-weight: 700;"
APP_SUBTITLE_QSS = "color: #A4B7DD; background: transparent; font-size: 11px;"
SECTION_TITLE_QSS = "color: #8EA7D5; background: transparent; font-size: 10px; font-weight: 600; padding-left: 12px; letter-spacing: 1px;"
AVATAR_QSS = qss("background: $PRIMARY; color: white; border-radius: 9px; font-size: 13px; font-weight: 600;")
USER_NAME_QSS = "color: white; background: transparent; font-size: 13px; font-weight: 600;"
USER_ROLE_QSS = "color: #A4B7DD; background: transparent; font-size: 11px;"
LOGOUT_BUTTON_QSS = """
    QPushButton { background: transparent; border: 1px solid transparent; border-radius: 6px; }
    QPushButton:hover { background: #284783; }
    QPushButton:focus { border-color: #6C91E0; }
"""
