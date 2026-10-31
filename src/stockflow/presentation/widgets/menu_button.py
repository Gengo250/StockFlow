import qtawesome as qta

from PySide6.QtWidgets import QPushButton

from PySide6.QtCore import QSize, Qt


def create_menu_button(text, icon_name, active=False):
    button = QPushButton(text)

    button.setIcon(
        qta.icon(
            icon_name,
            color="#BBD4FF"
        )
    )

    button.setCursor(Qt.PointingHandCursor)
    button.setIconSize(QSize(16, 16))
    button.setFixedHeight(42)

    if active:
        button.setObjectName("activeButton")

    return button
