"""Compatibility names for the shared StockFlow visual system."""
from .design_system import (
    TITLE_QSS, SUBTITLE_QSS, TABLE_QSS, LIST_STATE_QSS, LOAD_ERROR_QSS,
    button_qss, field_qss, page_qss, surface_qss,
)

PAGE_QSS = page_qss("estoquePage")
NEW_BUTTON_QSS = button_qss(primary=True)
SEARCH_QSS = field_qss("QLineEdit")
FILTER_QSS = button_qss()
TABLE_CARD_QSS = surface_qss("QFrame#tableCard, QFrame#card")
