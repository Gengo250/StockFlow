"""StockFlow visual foundations, shared by Qt pages and local components.

Selectors stay local to each page/component so status colors and the dark
navigation are not overwritten by a global application stylesheet.
"""
from pathlib import Path
from string import Template

BACKGROUND = "#F6F8FB"
SURFACE = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT = "#0F172A"
MUTED = "#64748B"
SUBTLE = "#94A3B8"
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
PRIMARY_SOFT = "#EFF6FF"
NAVY = "#102A6B"
PAGE_MARGIN = 24
SECTION_GAP = 20
CONTROL_HEIGHT = 40
ROW_HEIGHT = 48
_CONTROL_ASSETS = Path(__file__).resolve().parents[1] / "assets"


def qss(template, **values):
    """Expand explicit design tokens without rewriting arbitrary CSS colors."""
    return Template(template).substitute(
        BACKGROUND=BACKGROUND, SURFACE=SURFACE, BORDER=BORDER, TEXT=TEXT,
        MUTED=MUTED, SUBTLE=SUBTLE, PRIMARY=PRIMARY,
        PRIMARY_HOVER=PRIMARY_HOVER, PRIMARY_SOFT=PRIMARY_SOFT, NAVY=NAVY,
        **values,
    )


def page_layout(layout):
    layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
    layout.setSpacing(SECTION_GAP)


TITLE_QSS = qss("color: $TEXT; background: transparent; font-size: 24px; font-weight: 700;")
SUBTITLE_QSS = qss("color: $MUTED; background: transparent; font-size: 13px;")
SECTION_TITLE_QSS = qss("color: $TEXT; background: transparent; font-size: 16px; font-weight: 600;")
METRIC_QSS = qss("color: $TEXT; background: transparent; font-size: 26px; font-weight: 700;")

SCROLL_QSS = qss("""
    QScrollArea { background: $BACKGROUND; border: none; }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
    QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 3px; min-height: 28px; }
    QScrollBar::handle:vertical:hover { background: $SUBTLE; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
    QScrollBar:horizontal { background: transparent; height: 8px; margin: 2px; }
    QScrollBar::handle:horizontal { background: #CBD5E1; border-radius: 3px; min-width: 28px; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
""")


def field_qss(selector="QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit"):
    return qss("""
        $selector {
            background: $SURFACE; color: $TEXT; border: 1px solid $BORDER;
            border-radius: 8px; padding: 0 12px; font-size: 13px;
            selection-background-color: $PRIMARY; selection-color: white;
        }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
        QDoubleSpinBox:focus, QDateEdit:focus, QTextEdit:focus { border-color: $PRIMARY; }
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
        QDoubleSpinBox:disabled, QDateEdit:disabled {
            color: $SUBTLE; background: #F1F5F9; border-color: $BORDER;
        }
        QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 24px; }
        QComboBox::down-arrow, QDateEdit::down-arrow {
            image: url("$down_arrow"); width: 10px; height: 10px;
        }
        QComboBox QAbstractItemView {
            background: $SURFACE; color: $TEXT; border: 1px solid $BORDER;
            selection-background-color: $PRIMARY_SOFT; selection-color: $TEXT;
            padding: 4px;
        }
    """, selector=selector, down_arrow=(_CONTROL_ASSETS / "chevron-down.svg").as_posix())


def button_qss(selector="QPushButton", primary=False):
    return qss("""
        $selector {
            background: $fill; color: $ink; border: 1px solid $line;
            border-radius: 8px; padding: 0 16px; font-size: 13px; font-weight: 600;
        }
        $selector:hover { background: $hover; border-color: $hover_line; }
        $selector:pressed { background: $pressed; }
        $selector:focus:enabled { border: 2px solid #0F172A; }
        $selector:checked { background: $PRIMARY_SOFT; color: $PRIMARY; border-color: #BFDBFE; }
        $selector:disabled { background: #F1F5F9; color: $SUBTLE; border-color: $BORDER; }
    """, selector=selector, fill=PRIMARY if primary else SURFACE,
        ink="#FFFFFF" if primary else "#475569", line=PRIMARY if primary else BORDER,
        hover=PRIMARY_HOVER if primary else "#F8FAFC",
        hover_line=PRIMARY_HOVER if primary else "#CBD5E1",
        pressed="#1E40AF" if primary else "#F1F5F9")


def surface_qss(selector):
    return qss("""
        $selector { background: $SURFACE; border: 1px solid $BORDER; border-radius: 12px; }
    """, selector=selector)


def page_qss(*object_names):
    selectors = ", ".join(f"QWidget#{name}" for name in object_names)
    return qss("$selector { background: $BACKGROUND; }", selector=selectors) + qss("""
        QLabel { color: $TEXT; background: transparent; }
        QLabel#pageTitle { font-size: 24px; font-weight: 700; }
        QLabel#muted, QLabel#pageSubtitle { color: $MUTED; font-size: 13px; }
    """) + SCROLL_QSS


TABLE_QSS = qss("""
    QTableWidget { background: $SURFACE; color: $TEXT; border: none;
        font-size: 13px; gridline-color: $BORDER; selection-background-color: $PRIMARY_SOFT; }
    QTableWidget::viewport { background: $SURFACE; }
    QTableWidget::item { padding: 4px 10px; border: none; border-bottom: 1px solid #F1F5F9; }
    QTableWidget::item:selected { background: $PRIMARY_SOFT; color: $TEXT; }
    QTableWidget::item:hover { background: #F8FAFC; }
    QHeaderView::section {
        background: #F8FAFC; color: $MUTED; border: none;
        border-bottom: 1px solid $BORDER; padding: 12px 10px;
        font-size: 12px; font-weight: 600;
    }
    QTableCornerButton::section { background: #F8FAFC; border: none; }
""") + SCROLL_QSS

LIST_STATE_QSS = qss("color: $MUTED; background: transparent; font-size: 13px; padding: 24px 12px;")
LOAD_ERROR_QSS = """
    background: #FFF7ED; color: #9A3412; border: 1px solid #FED7AA;
    border-radius: 8px; padding: 16px; font-size: 13px;
"""


def status_badge_qss(foreground, background):
    return (f"color: {foreground}; background: {background}; border: none; "
            "border-radius: 6px; padding: 4px 8px; font-size: 12px; font-weight: 600;")


def directory_qss(page, form, card, action):
    return (page_qss(page, form) + field_qss() + TABLE_QSS
            + surface_qss(f"QFrame#{card}, QFrame#summaryCard")
            + button_qss("QPushButton#primaryButton", primary=True)
            + button_qss("QPushButton#secondaryButton")
            + button_qss(f"QPushButton#{action}") + qss("""
        QLineEdit, QComboBox { min-height: 38px; }
        QPushButton#primaryButton, QPushButton#secondaryButton { min-height: 38px; font-size: 13px; }
        QPushButton#iconButton { background: transparent; border: none; padding: 4px; min-height: 20px; }
        QPushButton#iconButton:hover { background: $PRIMARY_SOFT; border-radius: 6px; }
        QPushButton#iconButton:disabled { color: $SUBTLE; }
        QLabel#statusBadge { border-radius: 6px; padding: 4px 8px; font-size: 12px; font-weight: 600; }
        QLabel#statusBadge[status="Ativo"] { background: #ECFDF5; color: #047857; }
        QLabel#statusBadge[status="Inativo"] { background: #F1F5F9; color: #64748B; }
        QLabel#statusBadge[status="Pendente"] { background: #FFFBEB; color: #B45309; }
    """))
