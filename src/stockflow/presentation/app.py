import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from stockflow.presentation.windows.main_window import MainWindow
from stockflow.presentation.windows.login_window import LoginWindow


class LoginFlow:
    def __init__(self, settings=None):
        self.login = LoginWindow(settings)
        self.main = None
        self.login.authenticated.connect(self.open_main)

    def open_main(self):
        if self.main is None:
            try:
                self.main = MainWindow()
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
        self.login.reset()
        self.login.show()
        self.main.hide()


def run():
    app = QApplication(sys.argv)

    flow = LoginFlow()
    flow.login.show()

    return app.exec()
