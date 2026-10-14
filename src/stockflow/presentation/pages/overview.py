"""Resumo, exportação e preferências sobre os dados da sessão atual."""


from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QLabel,
    QHBoxLayout, QScrollArea, QFrame,
    QPushButton, QVBoxLayout, QWidget,
)

from stockflow.presentation.pages.dashboard import DashboardPage
from stockflow.presentation.pages.reports import ReportsPage
from stockflow.presentation.widgets.sidebar import DEFAULT_KEY
from stockflow.presentation.widgets.form_fields import _card, _card_header, _field, FIELD_QSS
from stockflow.presentation.styles import inventory


def preference_prefix(session):
    return f"users/{getattr(session, 'company_id', None) or 'demo'}/{getattr(session, 'user_id', None) or 'guest'}"


class SettingsPage(QWidget):
    def __init__(self, session, settings=None):
        super().__init__()
        self.settings = settings or QSettings("StockFlow", "StockFlow")
        self.prefix = preference_prefix(session)
        self.setObjectName("settingsPage")
        self.setStyleSheet("QWidget#settingsPage { background: #F0F5FF; } QLabel { background: transparent; color: #334155; }")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 24, 26, 24)
        outer.setSpacing(18)
        title = QLabel("Configurações")
        title.setStyleSheet(inventory.TITLE_QSS)
        outer.addWidget(title)
        subtitle = QLabel("Personalize sua experiência de trabalho neste dispositivo.")
        subtitle.setStyleSheet(inventory.SUBTITLE_QSS)
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        content = QWidget()
        content.setObjectName("settingsContent")
        content.setStyleSheet("QWidget#settingsContent { background: #F0F5FF; }")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(18)
        account = _card("settingsAccount")
        account.layout().addLayout(_card_header("fa5s.user-circle", "Conta e dispositivo", "As preferências são individuais para cada conta e empresa."))
        email = QLabel(getattr(session, "email", "") or "Sem sessão")
        email.setTextFormat(Qt.PlainText)
        email.setTextInteractionFlags(Qt.TextSelectableByMouse)
        email.setWordWrap(True)
        account.layout().addWidget(email)
        layout.addWidget(account)
        navigation = _card("settingsNavigation")
        navigation.layout().addLayout(_card_header("fa5s.desktop", "Área de trabalho", "Escolha a página exibida ao abrir o StockFlow."))
        self.start_page = QComboBox()
        for label, key in [("Dashboard", "dashboard"), ("Estoque", "estoque"), ("Produtos", "produtos"), ("Vendas", "vendas")]:
            self.start_page.addItem(label, key)
        # O padrão acompanha o item que a sidebar já nasce marcando como
        # ativo (DEFAULT_KEY). Divergir aqui abria a janela numa tela com o
        # menu apontando para outra.
        key = self.settings.value(self.prefix + "/start_page", DEFAULT_KEY)
        self.start_page.setCurrentIndex(max(0, self.start_page.findData(key)))
        self.start_page.setFixedHeight(42)
        self.start_page.setStyleSheet(FIELD_QSS.format(widget="QComboBox"))
        field = _field("Tela inicial")
        field.layout().addWidget(self.start_page)
        navigation.layout().addWidget(field)
        layout.addWidget(navigation)
        alerts = _card("settingsAlerts")
        alerts.layout().addLayout(_card_header("fa5s.bell", "Notificações de estoque", "Acompanhe os produtos que atingirem o estoque mínimo."))
        self.notifications = QCheckBox("Mostrar alertas de estoque")
        self.notifications.setChecked(self.settings.value(self.prefix + "/notifications", True, type=bool))
        self.notifications.setMinimumHeight(36)
        self.notifications.setCursor(Qt.PointingHandCursor)
        alerts.layout().addWidget(self.notifications)
        layout.addWidget(alerts)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        footer = QHBoxLayout()
        save = QPushButton("Salvar preferências")
        save.clicked.connect(self.save)
        save.setFixedHeight(42)
        save.setCursor(Qt.PointingHandCursor)
        save.setStyleSheet(inventory.NEW_BUTTON_QSS)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setStyleSheet("color: #166534; font-size: 13px;")
        footer.addWidget(self.feedback, 1)
        footer.addWidget(save)
        outer.addLayout(footer)

    def save(self):
        self.settings.setValue(self.prefix + "/start_page", self.start_page.currentData())
        self.settings.setValue(self.prefix + "/notifications", self.notifications.isChecked())
        self.settings.sync()
        self.feedback.setText("Preferências salvas neste dispositivo.")
