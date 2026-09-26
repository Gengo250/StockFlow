import sys

from PySide6.QtWidgets import QApplication

from stockflow.presentation.windows.main_window import MainWindow


def run():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    return app.exec()
