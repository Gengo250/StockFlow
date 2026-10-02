import sys

from PySide6.QtWidgets import QApplication

from stockflow.presentation.windows.main_window import MainWindow
from stockflow.presentation.windows.login_window import LoginWindow


class LoginFlow:
    def __init__(self, settings=None):
        self.login = LoginWindow(settings)
        self.main = None
        self.login.authenticated.connect(self.open_main)

    def open_main(self):
        if self.main is None:
            self.main = MainWindow()
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
