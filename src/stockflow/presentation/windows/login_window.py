import qtawesome as qta
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

# `autenticar` vem do seletor de backend, não de `demo_accounts`: é ele que
# decide entre as contas locais e o Supabase Auth. `DEMO_ACCOUNTS` continua
# vindo daqui porque só alimenta o aviso de "acesso à demonstração".
from stockflow.presentation.backend import authenticate as autenticar
from stockflow.presentation.demo_accounts import DEMO_ACCOUNTS, conta_admin
from stockflow.presentation.roles import rotulo_de_papel
from stockflow.presentation.styles.login import LOGIN_QSS


# Credencial fixa da demonstração. Antes vinha de DEMO_USERS[0][1], o que
# amarrava o login à ordem das linhas da tabela de Usuários: mexer naquela
# base trocava a senha de acesso do app sem que nada ali indicasse isso.
# Agora apontam para a conta ADMIN de `demo_accounts`, que é quem guarda o
# papel de cada conta — este módulo não pode ter uma segunda cópia da senha.
DEMO_EMAIL = conta_admin().email
DEMO_PASSWORD = conta_admin().password


def label(text, name, wrap=False):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


class LoginWindow(QWidget):
    # Carrega a `Session` do usuário: quem abre a janela principal precisa
    # saber o papel, e não só que alguém entrou.
    authenticated = Signal(object)

    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings if settings is not None else QSettings("StockFlow", "StockFlow")
        self.setObjectName("loginWindow")
        self.setWindowTitle("StockFlow — Acesse sua conta")
        self.setMinimumSize(440, 640)
        self.resize(1426, 878)
        self.setStyleSheet(LOGIN_QSS)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.brand = self._brand_panel()
        layout.addWidget(self.brand, 53)

        right = QWidget()
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(32, 24, 32, 24)
        right_layout.addStretch()
        right_layout.addWidget(self._form(), 1)
        right_layout.addStretch()
        layout.addWidget(right, 47)
        self.email_input.setFocus()

    def _brand_panel(self):
        panel = QFrame()
        panel.setObjectName("brandPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(48, 38, 48, 26)
        logo = QHBoxLayout()
        icon = label("", "brandIcon")
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("fa5s.cube", color="white").pixmap(22, 22))
        logo.addWidget(icon)
        name = QVBoxLayout()
        name.setSpacing(0)
        name.addWidget(label("StockFlow", "brandName"))
        name.addWidget(label("Gestão inteligente", "small"))
        logo.addLayout(name)
        logo.addStretch()
        layout.addLayout(logo)
        layout.addStretch(2)
        layout.addWidget(label("Tudo sob controle, em um só lugar", "badge"), 0, Qt.AlignLeft)
        layout.addSpacing(18)
        layout.addWidget(label("Decisões melhores\ncomeçam com um\nestoque organizado.", "headline", True))
        layout.addSpacing(12)
        layout.addWidget(label("Acompanhe vendas, produtos e movimentações\ncom uma visão clara de toda a sua operação.", "description", True))
        layout.addSpacing(28)
        features = QHBoxLayout()
        features.setSpacing(12)
        for title, subtitle in (("Produtos", "Catálogo organizado"), ("Estoque", "Visão da operação"), ("Gestão", "Tudo em um só lugar")):
            card = QFrame()
            card.setObjectName("feature")
            body = QVBoxLayout(card)
            body.setContentsMargins(14, 16, 14, 16)
            body.addWidget(label(title, "featureTitle"))
            body.addWidget(label(subtitle, "small", True))
            features.addWidget(card)
        layout.addLayout(features)
        layout.addStretch(2)
        layout.addWidget(label("StockFlow. Gestão simples, resultados reais.", "small"))
        return panel

    def _form(self):
        form = QWidget()
        form.setMaximumWidth(408)
        layout = QVBoxLayout(form)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()
        layout.addWidget(label("BEM-VINDO DE VOLTA", "eyebrow"))
        layout.addSpacing(14)
        layout.addWidget(label("Acesse sua conta", "title"))
        layout.addSpacing(6)
        layout.addWidget(label("Entre com suas credenciais para continuar.", "subtitle", True))
        layout.addSpacing(32)
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("seu.email@exemplo.com")
        self.email_input.setText(self.settings.value("login/email", "", type=str))
        self.email_input.setAccessibleName("E-mail")
        self.email_input.setMaxLength(254)
        self.email_input.setFixedHeight(46)
        self.email_input.addAction(qta.icon("fa5.envelope", color="#8ca1c2"), QLineEdit.LeadingPosition)
        email_label = label("E-mail", "fieldLabel")
        email_label.setBuddy(self.email_input)
        layout.addWidget(email_label)
        layout.addSpacing(8)
        layout.addWidget(self.email_input)
        layout.addSpacing(20)
        password_row = QHBoxLayout()
        password_label = label("Senha", "fieldLabel")
        password_row.addWidget(password_label)
        password_row.addStretch()
        help_button = QPushButton("Esqueceu a senha?")
        help_button.setObjectName("help")
        help_button.setCursor(Qt.PointingHandCursor)
        help_button.clicked.connect(self._show_access_help)
        password_row.addWidget(help_button)
        layout.addLayout(password_row)
        layout.addSpacing(8)
        self.password_input = QLineEdit()
        self.password_input.setAccessibleName("Senha")
        self.password_input.setPlaceholderText("Digite sua senha")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setFixedHeight(46)
        password_label.setBuddy(self.password_input)
        self.password_input.addAction(qta.icon("fa5s.lock", color="#8ca1c2"), QLineEdit.LeadingPosition)
        self.toggle_password = self.password_input.addAction(qta.icon("fa5.eye", color="#8ca1c2"), QLineEdit.TrailingPosition)
        self.toggle_password.setText("Mostrar senha")
        self.toggle_password.triggered.connect(self._toggle_password)
        layout.addWidget(self.password_input)
        layout.addSpacing(18)
        self.remember_email = QCheckBox("Lembrar e-mail")
        self.remember_email.setChecked(bool(self.email_input.text()))
        layout.addWidget(self.remember_email)
        self.error = label("", "error", True)
        self.error.setAccessibleName("Erro de login")
        self.error.setMinimumHeight(32)
        layout.addWidget(self.error)
        self.submit_button = QPushButton("Entrar no StockFlow  →")
        self.submit_button.setObjectName("submit")
        self.submit_button.setFixedHeight(48)
        self.submit_button.setCursor(Qt.PointingHandCursor)
        self.submit_button.clicked.connect(self._submit)
        self.email_input.returnPressed.connect(self._submit)
        self.password_input.returnPressed.connect(self._submit)
        layout.addWidget(self.submit_button)
        layout.addSpacing(26)
        footer = label("Acesso local · versão de demonstração", "footer")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)
        layout.addSpacing(16)
        demo = QPushButton("Como acessar a demonstração")
        demo.setObjectName("help")
        demo.clicked.connect(self._show_access_help)
        layout.addWidget(demo, 0, Qt.AlignCenter)
        layout.addStretch()
        return form

    def _toggle_password(self):
        visible = self.password_input.echoMode() == QLineEdit.Password
        self.password_input.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.toggle_password.setText("Ocultar senha" if visible else "Mostrar senha")
        self.toggle_password.setIcon(qta.icon("fa5.eye-slash" if visible else "fa5.eye", color="#8ca1c2"))

    def _show_access_help(self):
        from stockflow.presentation.backend import using_supabase
        if using_supabase():
            from stockflow.presentation.widgets.password_recovery import PasswordRecoveryDialog
            try:
                PasswordRecoveryDialog(self.email_input.text(), self).exec()
            except Exception:
                self.error.setText("Não foi possível abrir a recuperação. Confira a conexão.")
            return
        contas = "\n\n".join(
            f"{rotulo_de_papel(conta.role)} — {conta.name}\n"
            f"E-mail: {conta.email}\nSenha: {conta.password}"
            for conta in DEMO_ACCOUNTS
        )
        QMessageBox.information(
            self,
            "Acesso à demonstração",
            f"{contas}\n\nCada conta entra com um papel diferente: só "
            "Administrador e Estoque podem cadastrar ou editar produtos.\n"
            "Esta versão usa contas locais de demonstração.\n"
            "No modo Supabase, este botão recupera a senha por e-mail.",
        )

    def _submit(self):
        email = self.email_input.text().strip().casefold()
        password = self.password_input.text()
        if not email or not password:
            self.error.setText("Preencha o e-mail e a senha para entrar.")
            (self.email_input if not email else self.password_input).setFocus()
            return
        try:
            session = autenticar(email, password)
        except Exception as erro:
            # Falha de infraestrutura, não de credencial: conta do Auth sem
            # vínculo, usuário sem empresa, `.env` ausente ou servidor fora.
            # Digitar de novo não resolve nenhuma delas, então a senha NÃO é
            # limpa e a mensagem é a real — tratá-las como "senha incorreta"
            # mandaria o usuário tentar a mesma coisa indefinidamente.
            self.error.setText(str(erro))
            return
        if session is None:
            self.error.setText("E-mail ou senha incorretos. Tente novamente.")
            self.password_input.clear()
            self.password_input.setFocus()
            return
        self.settings.setValue("login/email", email if self.remember_email.isChecked() else "")
        self.reset()
        self.authenticated.emit(session)

    def reset(self):
        self.password_input.clear()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.toggle_password.setText("Mostrar senha")
        self.toggle_password.setIcon(qta.icon("fa5.eye", color="#8ca1c2"))
        self.error.clear()
        self.email_input.setFocus()

    def resizeEvent(self, event):
        self.brand.setVisible(event.size().width() >= 1100)
        super().resizeEvent(event)
