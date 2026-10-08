import qtawesome as qta
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QCompleter, QLineEdit, QListView, QToolTip


class SearchableComboBox(QComboBox):
    def __init__(self, placeholder):
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMaxVisibleItems(8)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(16)
        self.setView(QListView())
        self.lineEdit().setPlaceholderText(placeholder)
        self.lineEdit().setClearButtonEnabled(True)
        self.lineEdit().installEventFilter(self)
        self.setToolTip("Digite para buscar ou use a seta para ver a lista.")
        self.setStyleSheet("""
            QComboBox { background: white; border: 1px solid #CBDFFF; border-radius: 9px; padding: 8px 10px; }
            QComboBox:focus { border: 1px solid #2563EB; }
            QComboBox::drop-down { width: 0px; border: none; }
            QComboBox QLineEdit { background: transparent; border: none; padding: 0; color: #334155; }
        """)
        popup_style = """
            QAbstractItemView { background: white; color: #334155; border: 1px solid #CBDFFF;
                border-radius: 8px; padding: 6px; outline: 0; font-size: 13px;
                selection-background-color: #DBEAFE; selection-color: #1D4ED8; }
            QAbstractItemView::item { min-height: 34px; padding: 4px 10px; border-radius: 6px; }
            QAbstractItemView::item:hover { background: #EFF6FF; }
        """
        self.completer().setFilterMode(Qt.MatchContains)
        self.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.completer().setMaxVisibleItems(8)
        for popup in (self.view(), self.completer().popup()):
            popup.setStyleSheet(popup_style)
            popup.setMinimumWidth(340)
            popup.setTextElideMode(Qt.ElideRight)
        arrow = self.lineEdit().addAction(
            qta.icon("fa5s.chevron-down", color="#64748B"), QLineEdit.TrailingPosition
        )
        arrow.setToolTip("Mostrar opções")
        arrow.triggered.connect(self.showPopup)

    def showPopup(self):
        if self.count() <= 1:
            QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), "Nenhuma opção disponível.", self)
            return
        self.view().setRowHidden(0, True)
        super().showPopup()

    def eventFilter(self, watched, event):
        if watched is self.lineEdit() and event.type() == QEvent.FocusIn:
            QTimer.singleShot(0, self.lineEdit().selectAll)
        return super().eventFilter(watched, event)
