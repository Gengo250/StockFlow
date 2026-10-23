"""Access screens share the application palette and controls."""
from .design_system import qss, field_qss, button_qss

LOGIN_QSS = field_qss("QLineEdit") + button_qss("QPushButton#submit", primary=True) + qss("""
QWidget#loginWindow { background: $BACKGROUND; }
QLabel, QCheckBox { font-size: 13px; color: #475569; background: transparent; }
QFrame#brandPanel { background: $NAVY; border: none; }
QFrame#brandPanel QLabel { color: #B7C8E7; }
QWidget#loginWindow QLabel#brandName { color: white; font-size: 20px; font-weight: 700; }
QWidget#loginWindow QLabel#brandIcon { background: #284C9C; border: none; border-radius: 10px; }
QWidget#loginWindow QLabel#badge { background: #23417B; border: 1px solid #36548A; border-radius: 6px; padding: 6px 12px; font-size: 11px; color: white; }
QWidget#loginWindow QLabel#headline { color: white; font-size: 40px; font-weight: 700; }
QWidget#loginWindow QLabel#description { font-size: 14px; }
QFrame#feature { background: #193574; border: 1px solid #2C4780; border-radius: 12px; }
QWidget#loginWindow QLabel#featureTitle { color: white; font-size: 17px; font-weight: 600; }
QWidget#loginWindow QLabel#small { font-size: 11px; }
QWidget#loginWindow QLabel#eyebrow { color: $PRIMARY; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QWidget#loginWindow QLabel#title { color: $TEXT; font-size: 28px; font-weight: 700; }
QWidget#loginWindow QLabel#subtitle { color: $MUTED; }
QWidget#loginWindow QLabel#fieldLabel { color: #475569; font-size: 13px; font-weight: 600; }
QPushButton { font-size: 13px; }
QPushButton#help { background: transparent; border: none; color: $PRIMARY; font-size: 12px; text-align: right; }
QPushButton#help:hover { text-decoration: underline; }
QPushButton#help:focus { border-bottom: 1px solid $PRIMARY; }
QWidget#loginWindow QLabel#error { color: #B42318; font-size: 12px; }
QWidget#loginWindow QLabel#footer { color: $MUTED; font-size: 11px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid $SUBTLE; border-radius: 3px; background: white; }
QCheckBox::indicator:checked { background: $PRIMARY; border-color: $PRIMARY; }
QCheckBox:focus { color: $PRIMARY; }
""")
