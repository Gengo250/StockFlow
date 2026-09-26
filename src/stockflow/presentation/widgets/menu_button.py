import qtawesome as qta

from PySide6.QtWidgets import QPushButton

from PySide6.QtCore import QSize


def create_menu_button(text, icon_name, active=False):
    button = QPushButton(text)

    button.setIcon(
        qta.icon(
            icon_name,
            color="#BBD4FF"
        )
    )

    button.setIconSize(QSize(18, 18))
    button.setFixedHeight(42)

    if active:
        button.setObjectName("activeButton")

    return button
