"""Recuperação de acesso com sessão Auth isolada do aplicativo."""

from urllib.parse import parse_qs, urlparse

from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton

from stockflow.presentation.backend import independent_auth_client


class PasswordRecoveryDialog(QDialog):
    def __init__(self, email="", parent=None, client=None):
        super().__init__(parent)
        self.client = client or independent_auth_client()
        self.setWindowTitle("Recuperar acesso")
        self.setMinimumWidth(460)
        layout = QFormLayout(self)
        self.email_input = QLineEdit(email)
        layout.addRow("E-mail", self.email_input)
        send = QPushButton("Enviar recuperação por e-mail")
        send.clicked.connect(self.send)
        layout.addRow(send)
        instructions = QLabel("Copie o link de recuperação recebido no e-mail, sem abri-lo, e cole abaixo. Se recebeu um código, pode usá-lo aqui.")
        instructions.setWordWrap(True)
        layout.addRow(instructions)
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.Password)
        layout.addRow("Link ou código", self.token_input)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addRow("Nova senha", self.password_input)
        save = QPushButton("Definir nova senha")
        save.clicked.connect(self.save)
        layout.addRow(save)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addRow(self.message)

    def send(self):
        email = self.email_input.text().strip()
        if "@" not in email:
            self.message.setText("Informe o e-mail da conta.")
            return
        try:
            self.client.auth.reset_password_email(email)
            self.message.setText("Solicitação enviada. Verifique seu e-mail.")
        except Exception:
            self.message.setText("Não foi possível enviar. Verifique a conexão e tente novamente mais tarde.")

    def save(self):
        token = self.token_input.text().strip()
        password = self.password_input.text()
        if len(password) < 6 or not token:
            self.message.setText("Informe o link/código e uma senha de pelo menos 6 caracteres.")
            return
        try:
            if token.startswith("https://"):
                query = parse_qs(urlparse(token).query)
                if query.get("type", [None])[0] != "recovery":
                    raise ValueError("Link não é de recuperação")
                token_hash = query.get("token_hash", query.get("token", [""]))[0]
                if not token_hash:
                    raise ValueError("Link sem token")
                # Never fetch a pasted URL; only send its token to the configured Auth.
                self.client.auth.verify_otp({"token_hash": token_hash, "type": "recovery"})
            else:
                self.client.auth.verify_otp({"email": self.email_input.text().strip(), "token": token, "type": "recovery"})
            self.client.auth.update_user({"password": password})
            self.password_input.clear()
            self.token_input.clear()
            self.message.setText("Senha atualizada. Feche esta janela e entre com a nova senha.")
        except Exception:
            self.message.setText("Não foi possível atualizar. Confira o código/link, sua validade e os requisitos de senha.")
        finally:
            try:
                self.client.auth.sign_out()
            except Exception:
                pass
