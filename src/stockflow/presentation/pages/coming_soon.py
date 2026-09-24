import qtawesome as qta

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
)

from PySide6.QtCore import Qt


class ComingSoonPage(QWidget):

    def __init__(self, title):
        super().__init__()

        self.setObjectName("comingSoonPage")

        self.setStyleSheet("""
    QWidget#comingSoonPage {
        background-color: #F0F5FF;
    }
""")

        # Layout principal
        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            40,
            40,
            40,
            40
        )

        main_layout.setAlignment(Qt.AlignCenter)


        # ==================================================
        # CARD CENTRAL
        # ==================================================

        card = QFrame()

        card.setFixedWidth(520)

        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;

                border: 1px solid #DBEAFE;
                border-radius: 20px;
            }
        """)

        card_layout = QVBoxLayout(card)

        card_layout.setContentsMargins(
            40,
            38,
            40,
            38
        )

        card_layout.setSpacing(12)

        card_layout.setAlignment(Qt.AlignCenter)


        # ==================================================
        # ÍCONE
        # ==================================================

        icon_container = QFrame()

        icon_container.setFixedSize(72, 72)

        icon_container.setStyleSheet("""
            background-color: #EFF6FF;

            border: 1px solid #BFDBFE;
            border-radius: 18px;
        """)

        icon_layout = QVBoxLayout(icon_container)

        icon_layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel()

        icon_label.setAlignment(Qt.AlignCenter)

        icon_label.setPixmap(
            qta.icon(
                "fa5s.tools",
                color="#2563EB"
            ).pixmap(30, 30)
        )

        icon_layout.addWidget(icon_label)


        # ==================================================
        # STATUS
        # ==================================================

        status_container = QFrame()

        status_container.setStyleSheet("""
            background-color: #EFF6FF;

            border: 1px solid #BFDBFE;
            border-radius: 12px;
        """)

        status_layout = QHBoxLayout(status_container)

        status_layout.setContentsMargins(
            10,
            5,
            10,
            5
        )

        status_layout.setSpacing(6)


        status_dot = QLabel("●")

        status_dot.setStyleSheet("""
            color: #3B82F6;
            font-size: 10px;
            border: none;
        """)


        status_text = QLabel("EM DESENVOLVIMENTO")

        status_text.setStyleSheet("""
            color: #2563EB;

            font-size: 11px;
            font-weight: 600;

            border: none;
        """)


        status_layout.addWidget(status_dot)
        status_layout.addWidget(status_text)


        # ==================================================
        # TÍTULO
        # ==================================================

        title_label = QLabel(title)

        title_label.setAlignment(Qt.AlignCenter)

        title_label.setStyleSheet("""
            color: #0F172A;

            font-size: 30px;
            font-weight: 700;

            border: none;
        """)


        # ==================================================
        # MENSAGEM
        # ==================================================

        message = QLabel(
            "Estamos preparando esta área do Atlas.\n"
            "Novas funcionalidades estarão disponíveis em breve."
        )

        message.setAlignment(Qt.AlignCenter)

        message.setWordWrap(True)

        message.setStyleSheet("""
            color: #64748B;

            font-size: 14px;

            border: none;
        """)


        # ==================================================
        # TEXTO SECUNDÁRIO
        # ==================================================

        secondary_message = QLabel(
            "Enquanto isso, utilize o Dashboard para acompanhar "
            "as principais informações do sistema."
        )

        secondary_message.setAlignment(Qt.AlignCenter)

        secondary_message.setWordWrap(True)

        secondary_message.setStyleSheet("""
            color: #94A3B8;

            font-size: 12px;

            border: none;
        """)


        # ==================================================
        # MONTA CARD
        # ==================================================

        card_layout.addWidget(
            icon_container,
            alignment=Qt.AlignCenter
        )

        card_layout.addSpacing(10)

        card_layout.addWidget(
            status_container,
            alignment=Qt.AlignCenter
        )

        card_layout.addSpacing(6)

        card_layout.addWidget(title_label)

        card_layout.addWidget(message)

        card_layout.addSpacing(6)

        card_layout.addWidget(secondary_message)


        # ==================================================
        # ADICIONA CARD À PÁGINA
        # ==================================================

        main_layout.addWidget(
            card,
            alignment=Qt.AlignCenter
        )