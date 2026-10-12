"""Cadastro rápido de fornecedores e clientes no modo demonstrativo."""
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from stockflow.presentation.styles.users import USERS_QSS


class PartyForm(QDialog):
    def __init__(self, is_supplier, parent=None):
        super().__init__(parent)
        party = 'fornecedor' if is_supplier else 'cliente'
        self.setWindowTitle(f'Cadastrar novo {party}')
        self.setObjectName('partyForm')
        self.setStyleSheet(USERS_QSS.replace('QDialog#userForm', 'QDialog#partyForm'))
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        title = QLabel(self.windowTitle())
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        hint = QLabel('Modo demonstrativo: o cadastro fica disponível apenas nesta sessão.')
        hint.setObjectName('muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        fields = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setMaxLength(120)
        self.name_input.setPlaceholderText(f'Nome do {party}')
        self.name_input.setAccessibleName(f'Nome do {party}')
        fields.addRow('Nome *', self.name_input)
        layout.addLayout(fields)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton('Cancelar')
        self.cancel_button.setObjectName('secondaryButton')
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton(f'Cadastrar {party}')
        self.save_button.setObjectName('primaryButton')
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.name_input.setFocus()

    def accept(self):
        if not self.name_input.text().strip():
            self.error_label.setText('Informe um nome para continuar.')
            self.name_input.setFocus()
            return
        super().accept()
