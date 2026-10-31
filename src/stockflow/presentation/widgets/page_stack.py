"""Navegação com rolagem independente, sem ampliar a janela para caber páginas."""

from stockflow.presentation.styles import design_system as ds
from PySide6.QtWidgets import QFrame, QScrollArea, QStackedWidget


class PageStack(QStackedWidget):
    """Expõe as páginas à navegação e mantém seus contêineres internamente."""

    def addWidget(self, page):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(ds.SCROLL_QSS)
        scroll.setWidget(page)
        return super().addWidget(scroll)

    def widget(self, index):
        scroll = super().widget(index)
        return scroll.widget() if scroll is not None else None

    def currentWidget(self):
        return self.widget(self.currentIndex())

    def indexOf(self, page):
        return next((i for i in range(self.count()) if self.widget(i) is page), -1)

    def setCurrentWidget(self, page):
        index = self.indexOf(page)
        if index >= 0:
            self.setCurrentIndex(index)
