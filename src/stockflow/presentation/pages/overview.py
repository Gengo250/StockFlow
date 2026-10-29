"""Resumo, exportação e preferências sobre os dados da sessão atual."""

from stockflow.presentation.styles import design_system as ds


from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QLabel,
    QHBoxLayout, QScrollArea, QFrame,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from stockflow.presentation.pages.dashboard import DashboardPage
from stockflow.presentation.pages.reports import ReportsPage
from stockflow.presentation.widgets.sidebar import DEFAULT_KEY
from stockflow.presentation.widgets.form_fields import _card, _card_header, _field, FIELD_QSS
from stockflow.presentation.styles import inventory
from stockflow.domain.permissions import can_manage_companies


def preference_prefix(session):
    return f"users/{getattr(session, 'company_id', None) or 'demo'}/{getattr(session, 'user_id', None) or 'guest'}"


class SettingsPage(QWidget):
    discount_limits_save_requested = Signal(str)

    def __init__(self, session, settings=None):
        super().__init__()
        self.settings = settings or QSettings("StockFlow", "StockFlow")
        self.prefix = preference_prefix(session)
        self.setObjectName("settingsPage")
        self.setStyleSheet(ds.page_qss("settingsPage"))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN, ds.PAGE_MARGIN)
        outer.setSpacing(ds.SECTION_GAP)
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
        scroll.setStyleSheet(ds.SCROLL_QSS)
        content = QWidget()
        content.setObjectName("settingsContent")
        content.setStyleSheet(ds.page_qss("settingsContent"))
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(ds.SECTION_GAP)
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
        self.start_page.setFixedHeight(ds.CONTROL_HEIGHT)
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
        discount_limits = _card("settingsSaleDiscountLimits")
        discount_limits.layout().addLayout(_card_header(
            "fa5s.percentage",
            "Limites de desconto em vendas",
            "Descontos acima do limite do vendedor exigem aprovação de ADMIN.",
        ))
        self.seller_discount_limit = QLineEdit()
        self.seller_discount_limit.setPlaceholderText("10")
        self.seller_discount_limit.setFixedHeight(ds.CONTROL_HEIGHT)
        self.seller_discount_limit.setStyleSheet(
            FIELD_QSS.format(widget="QLineEdit")
        )
        discount_field = _field("Limite do perfil Vendedor (%)")
        discount_field.layout().addWidget(self.seller_discount_limit)
        discount_limits.layout().addWidget(discount_field)
        discount_limits_footer = QHBoxLayout()
        self.discount_limits_feedback = QLabel()
        self.discount_limits_feedback.setWordWrap(True)
        self.discount_limits_feedback.setStyleSheet(
            "color: #166534; font-size: 13px;"
        )
        self.save_discount_limits_button = QPushButton(
            "Salvar limite de desconto"
        )
        self.save_discount_limits_button.setFixedHeight(ds.CONTROL_HEIGHT)
        self.save_discount_limits_button.setStyleSheet(inventory.NEW_BUTTON_QSS)
        self.save_discount_limits_button.clicked.connect(
            self._request_discount_limits_save
        )
        discount_limits_footer.addWidget(self.discount_limits_feedback, 1)
        discount_limits_footer.addWidget(self.save_discount_limits_button)
        discount_limits.layout().addLayout(discount_limits_footer)
        self.discount_limits_card = discount_limits
        layout.addWidget(discount_limits)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        footer = QHBoxLayout()
        save = QPushButton("Salvar preferências")
        save.clicked.connect(self.save)
        save.setFixedHeight(ds.CONTROL_HEIGHT)
        save.setCursor(Qt.PointingHandCursor)
        save.setStyleSheet(inventory.NEW_BUTTON_QSS)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setStyleSheet("color: #166534; font-size: 13px;")
        footer.addWidget(self.feedback, 1)
        footer.addWidget(save)
        outer.addLayout(footer)
        self.apply_session(session)

    def apply_session(self, session):
        allowed = can_manage_companies(session)
        self.discount_limits_card.setVisible(allowed)
        self.save_discount_limits_button.setEnabled(allowed)

    def set_discount_limits(self, limits):
        value = limits.get("SELLER")
        self.seller_discount_limit.setText(
            "10" if value is None else str(value).replace(".", ",")
        )
        self.discount_limits_feedback.setStyleSheet(
            "color: #166534; font-size: 13px;"
        )
        self.discount_limits_feedback.setText("Limites carregados.")

    def show_discount_limits_error(self, error):
        self.discount_limits_feedback.setStyleSheet(
            "color: #B91C1C; font-size: 13px;"
        )
        self.discount_limits_feedback.setText(
            f"Não foi possível carregar/salvar o limite: {error}"
        )

    def _request_discount_limits_save(self):
        self.discount_limits_feedback.setText("")
        self.discount_limits_save_requested.emit(
            self.seller_discount_limit.text().strip()
        )

    def save(self):
        self.settings.setValue(self.prefix + "/start_page", self.start_page.currentData())
        self.settings.setValue(self.prefix + "/notifications", self.notifications.isChecked())
        self.settings.sync()
        self.feedback.setText("Preferências salvas neste dispositivo.")
