import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from stockflow.presentation.windows.main_window import MainWindow
from stockflow.presentation import backend
from stockflow.presentation.windows.login_window import LoginWindow


class LoginFlow:
    def __init__(self, settings=None):
        self.login = LoginWindow(settings)
        self.main = None
        self.login.authenticated.connect(self.open_main)

    def open_main(self, session):
        # Sem valor padrão de propósito: `session=None` fazia os dois ramos
        # falharem abertos — a janela nova nascia com a sessão ausente e a
        # janela reaproveitada mantinha as permissões do usuário anterior.
        # O sinal `authenticated` sempre entrega uma sessão; chamar sem ela
        # agora é um TypeError, e não um acesso concedido em silêncio.
        if self.main is not None:
            self.main.close()
            self.main = None
        if self.main is None:
            try:
                self.main = MainWindow(session)
            except Exception:
                # Slot do Qt: uma exceção aqui só vai para o stderr e o
                # controle volta para a janela de login intacta. Sem este
                # aviso, entrar com a conta de demonstração parecia um
                # travamento — o botão respondia e nada acontecia.
                traceback.print_exc()
                self.login.error.setText(
                    "Não foi possível abrir o StockFlow. Veja os detalhes no aviso."
                )
                QMessageBox.critical(
                    self.login,
                    "Erro ao abrir o StockFlow",
                    "A autenticação funcionou, mas a janela principal não pôde ser "
                    "construída.\n\nDetalhes técnicos:\n"
                    f"{traceback.format_exc(limit=0).strip()}",
                )
                return
            self.main.sidebar.logout_button.clicked.connect(self.logout)
        self.main.show()
        self.login.hide()

    def logout(self):
        # Drop the complete tenant context, even if revoking the remote session fails.
        if self.main is not None:
            self.main.close()
            self.main = None
        self.login.reset()
        try:
            backend.sign_out()
        except Exception:
            self.login.error.setText("Sessão local encerrada. Não foi possível confirmar a saída no servidor.")
        self.login.show()


def run():
    app = QApplication(sys.argv)

    flow = LoginFlow()
    flow.login.show()

    return app.exec()
