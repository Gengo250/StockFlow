import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget
from stockflow.presentation.demo_users import DEMO_USERS


class UserSummary(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        cards = (
            ("Administrador", "Administradores", "fa5s.shield-alt", "#8129FF"),
            ("Estoquista", "Estoquistas", "fa5s.boxes", "#195BFF"),
            ("Financeiro", "Financeiro", "fa5s.wallet", "#FF9500"),
        )
        for column, (role, title, icon, color) in enumerate(cards):
            card = QFrame()
            card.setObjectName("summaryCard")
            card.setFixedHeight(174)
            content = QVBoxLayout(card)
            content.setContentsMargins(18, 18, 18, 18)
            content.setSpacing(8)
            badge = QLabel()
            badge.setFixedSize(36, 36)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(f"background: {color}; border-radius: 11px;")
            badge.setPixmap(qta.icon(icon, color="white").pixmap(18, 18))
            number = QLabel(str(sum(user[2] == role for user in DEMO_USERS)))
            number.setStyleSheet(f"color: {color}; font-size: 27px; font-weight: 600;")
            caption = QLabel(title)
            caption.setObjectName("muted")
            content.addWidget(badge)
            content.addSpacing(4)
            content.addWidget(number)
            content.addWidget(caption)
            content.addStretch()
            layout.addWidget(card, 0, column)
            layout.setColumnStretch(column, 1)
