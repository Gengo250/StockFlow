import qtawesome as qta
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget


class UserSummary(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        cards = (
            ("8", "Total de usuários", "fa5s.users", "#195BFF"),
            ("6", "Usuários ativos", "fa5s.check-circle", "#00B887"),
            ("1", "Administradores", "fa5s.shield-alt", "#8129FF"),
            ("1", "Convites pendentes", "fa5s.envelope", "#FF9500"),
        )
        for column, (value, title, icon, color) in enumerate(cards):
            card = QFrame()
            card.setObjectName("summaryCard")
            content = QVBoxLayout(card)
            content.setContentsMargins(18, 18, 18, 18)
            content.setSpacing(8)
            badge = QLabel()
            badge.setFixedSize(36, 36)
            badge.setStyleSheet(f"background: {color}; border-radius: 11px; padding: 9px;")
            badge.setPixmap(qta.icon(icon, color="white").pixmap(18, 18))
            number = QLabel(value)
            number.setStyleSheet(f"color: {color}; font-size: 27px; font-weight: 600;")
            caption = QLabel(title)
            caption.setObjectName("muted")
            content.addWidget(badge)
            content.addSpacing(4)
            content.addWidget(number)
            content.addWidget(caption)
            layout.addWidget(card, 0, column)
            layout.setColumnStretch(column, 1)
