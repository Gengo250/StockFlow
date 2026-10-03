LOGIN_QSS = """
QWidget#loginWindow { background: #f7f9ff; }
QLabel, QCheckBox {
    font-family: 'Inter', 'DejaVu Sans'; font-size: 13px; color: #354561;
    background: transparent;
}
QFrame#brandPanel {
    background: qlineargradient(x1:0, y1:1, x2:1, y2:0,
        stop:0 #174681, stop:0.5 #19387e, stop:1 #244d96);
}
QFrame#brandPanel QLabel { color: #bdcdec; }
QWidget#loginWindow QLabel#brandName { color: white; font-size: 20px; font-weight: 700; }
QWidget#loginWindow QLabel#brandIcon { background: rgba(255, 255, 255, 34); border: 1px solid rgba(255, 255, 255, 68); border-radius: 14px; }
QWidget#loginWindow QLabel#badge { background: rgba(255, 255, 255, 24); border: 1px solid rgba(255, 255, 255, 51); border-radius: 14px; padding: 6px 12px; font-size: 11px; color: white; }
QWidget#loginWindow QLabel#headline { color: white; font-size: 43px; font-weight: 700; }
QWidget#loginWindow QLabel#description { font-size: 15px; }
QFrame#feature { background: rgba(255, 255, 255, 24); border: 1px solid rgba(255, 255, 255, 40); border-radius: 15px; }
QWidget#loginWindow QLabel#featureTitle { color: white; font-size: 19px; font-weight: 700; }
QWidget#loginWindow QLabel#small { font-size: 11px; }
QWidget#loginWindow QLabel#eyebrow { color: #195bff; font-size: 11px; font-weight: 600; letter-spacing: 2px; }
QWidget#loginWindow QLabel#title { color: #121b30; font-size: 28px; font-weight: 700; }
QWidget#loginWindow QLabel#subtitle { color: #667b9e; }
QLineEdit { background: white; color: #354561; border: 1px solid #d4e2ff; border-radius: 11px; padding: 0 12px; font-size: 13px; selection-background-color: #195bff; }
QLineEdit:focus { border: 2px solid #195bff; }
QPushButton { font-size: 13px; }
QPushButton#submit { background: #195bff; color: white; border: none; border-radius: 11px; font-size: 15px; font-weight: 600; }
QPushButton#submit:hover { background: #104be0; }
QPushButton#submit:pressed { background: #153db2; }
QPushButton#submit:focus { border: 2px solid #12317d; }
QPushButton#help { background: transparent; border: none; color: #195bff; font-size: 11px; text-align: right; }
QPushButton#help:hover { text-decoration: underline; }
QWidget#loginWindow QLabel#error { color: #b42318; font-size: 12px; }
QWidget#loginWindow QLabel#footer { color: #879bbc; font-size: 11px; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #8ca1c2; border-radius: 2px; background: white; }
QCheckBox::indicator:checked { background: #195bff; border: 1px solid #195bff; }
QCheckBox:focus { color: #195bff; }
"""
