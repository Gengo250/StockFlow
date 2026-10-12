import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from stockflow.presentation.styles.settings import SETTINGS_QSS
from stockflow.presentation.widgets.form_fields import (
    _card, _card_header, _divider, _field, _line_edit,
)


class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("settingsPage")
        self.setStyleSheet(SETTINGS_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("settingsContent")
        body = QVBoxLayout(content)
        body.setContentsMargins(28, 26, 28, 32)
        body.setSpacing(20)

        title = QLabel("Configurações do sistema")
        title.setObjectName("settingsTitle")
        body.addWidget(title)
        subtitle = QLabel("Organize os dados da empresa e as preferências da operação.")
        subtitle.setObjectName("settingsSubtitle")
        subtitle.setWordWrap(True)
        body.addWidget(subtitle)

        notice = QLabel(
            "Prévia de configurações • Os campos abaixo são demonstrativos. "
            "As alterações não são salvas e não afetam o estoque."
        )
        notice.setObjectName("settingsNotice")
        notice.setWordWrap(True)
        body.addWidget(notice)
        body.addWidget(self._company_card())
        body.addWidget(self._inventory_card())
        body.addWidget(self._system_card())

        footer = QHBoxLayout()
        self.feedback = QLabel()
        self.feedback.setObjectName("settingsSubtitle")
        self.feedback.setWordWrap(True)
        footer.addWidget(self.feedback, 1)
        self.reset_button = QPushButton("Restaurar prévia")
        self.reset_button.setIcon(qta.icon("fa5s.undo", color="#2563EB"))
        self.reset_button.setCursor(Qt.PointingHandCursor)
        self.reset_button.clicked.connect(self._reset_preview)
        footer.addWidget(self.reset_button)
        body.addLayout(footer)
        body.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _company_card(self):
        card = _card("companySettingsCard")
        layout = card.layout()
        layout.addLayout(_card_header(
            "fa5s.building", "Dados da empresa", "Identificação e contato da sua operação."
        ))
        layout.addWidget(_divider())
        self.company_name = _line_edit("Nome da empresa")
        self.company_email = _line_edit("contato@empresa.com.br")
        for title, field in (
            ("Nome da empresa", self.company_name),
            ("E-mail de contato", self.company_email),
        ):
            container = _field(title)
            container.layout().addWidget(field)
            field.setAccessibleName(title)
            layout.addWidget(container)
        return card

    def _inventory_card(self):
        card = _card("inventorySettingsCard")
        layout = card.layout()
        layout.addLayout(_card_header(
            "fa5s.boxes", "Preferências de estoque", "Prévia das opções de controle de produtos."
        ))
        layout.addWidget(_divider())
        self.low_stock = self._option(
            layout, "Alertas de estoque baixo",
            "Destacar produtos que atingirem o estoque mínimo.", True,
        )
        layout.addWidget(_divider())
        self.confirm_movements = self._option(
            layout, "Confirmação de movimentações",
            "Solicitar confirmação antes de registrar entradas e saídas.", True,
        )
        return card

    @staticmethod
    def _option(layout, title, description, checked):
        option = QCheckBox(title)
        option.setChecked(checked)
        option.setCursor(Qt.PointingHandCursor)
        option.setAccessibleDescription(description)
        layout.addWidget(option)
        hint = QLabel(description)
        hint.setWordWrap(True)
        hint.setObjectName("settingsSubtitle")
        layout.addWidget(hint)
        return option

    def _system_card(self):
        card = _card("systemSettingsCard")
        layout = card.layout()
        layout.addLayout(_card_header(
            "fa5s.desktop", "Sobre o sistema", "Informações da versão atual do StockFlow."
        ))
        layout.addWidget(_divider())
        for label, value in (
            ("Idioma da interface", "Português (Brasil)"),
            ("Moeda", "Real brasileiro (R$)"),
            ("Ambiente", "Demonstração local"),
            ("Armazenamento", "Dados demonstrativos, sem banco integrado"),
        ):
            row = QHBoxLayout()
            caption = QLabel(label)
            caption.setObjectName("settingsSubtitle")
            detail = QLabel(value)
            detail.setWordWrap(True)
            row.addWidget(caption, 1)
            row.addWidget(detail, 2)
            layout.addLayout(row)
        return card

    def _reset_preview(self):
        self.company_name.clear()
        self.company_email.clear()
        self.low_stock.setChecked(True)
        self.confirm_movements.setChecked(True)
        self.feedback.setText("Prévia restaurada para os valores iniciais.")

