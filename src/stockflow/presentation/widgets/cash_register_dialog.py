"""Abertura e conferência do caixa sem bloquear a interface durante I/O."""
from decimal import Decimal

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)
from stockflow.application.services.cash_register_service import PAYMENT_LABELS
from stockflow.presentation.styles import design_system as ds
from stockflow.presentation.workers import executar_agora


class CashRegisterDialog(QDialog):
    def __init__(self, service, parent=None, execute=executar_agora):
        super().__init__(parent)
        self.service, self.execute = service, execute
        self.current = None
        self._busy = False
        self._state_known = False
        self.setWindowTitle('Caixa')
        self.setMinimumWidth(560)
        self.setObjectName('cashRegisterDialog')
        self.setStyleSheet(ds.page_qss('cashRegisterDialog') + ds.field_qss() + ds.button_qss())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        self.status = QLabel('Consulte a situação do seu caixa.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.open_form = QWidget()
        form = QFormLayout(self.open_form)
        self.initial_balance = self._amount()
        form.addRow('Saldo inicial / troco', self.initial_balance)
        layout.addWidget(self.open_form)
        self.close_form = QWidget()
        form = QFormLayout(self.close_form)
        self.declared = {}
        for key, label in PAYMENT_LABELS.items():
            self.declared[key] = self._amount()
            form.addRow(label, self.declared[key])
        self.justification = QLineEdit()
        self.justification.setPlaceholderText('Obrigatória quando houver diferença')
        self.justification.setMaxLength(2000)
        self.justification.setMinimumHeight(34)
        form.addRow('Justificativa', self.justification)
        layout.addWidget(self.close_form)
        self.close_form.hide()
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(Qt.PlainText)
        layout.addWidget(self.feedback)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton('Atualizar')
        self.action_button = QPushButton('Iniciar caixa')
        self.action_button.setStyleSheet(ds.button_qss(primary=True))
        self.action_button.setEnabled(False)
        self.dismiss_button = QPushButton('Voltar')
        for button in (self.refresh_button, self.action_button, self.dismiss_button):
            button.setMinimumHeight(36)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.refresh_button.clicked.connect(self.refresh)
        self.action_button.clicked.connect(self.submit)
        self.dismiss_button.clicked.connect(self.reject)

    @staticmethod
    def _amount():
        field = QDoubleSpinBox()
        field.setLocale(QLocale('pt_BR'))
        field.setRange(0, 99999999.99)
        field.setDecimals(2)
        field.setPrefix('R$ ')
        field.setButtonSymbols(QAbstractSpinBox.NoButtons)
        field.setMinimumHeight(34)
        return field

    def reject(self):
        if not self._busy:
            super().reject()

    def _run(self, operation, success):
        if self._busy:
            return
        self._busy = True
        self.feedback.setText('Aguarde…')
        for widget in (self.open_form, self.close_form, self.action_button,
                       self.refresh_button, self.dismiss_button):
            widget.setEnabled(False)

        def finish():
            self._busy = False
            for widget in (self.open_form, self.close_form, self.refresh_button, self.dismiss_button):
                widget.setEnabled(True)

        def loaded(result):
            finish()
            success(result)

        def failed(error):
            finish()
            self.feedback.setText(str(error))
            self.action_button.setEnabled(self._state_known)

        self.execute(operation, loaded, failed)

    def refresh(self):
        self._state_known = False
        self._run(self.service.current, self._loaded)

    def _loaded(self, current):
        self.current = current
        self._state_known = True
        opened = bool(current)
        self.status.setText(
            f"Caixa aberto · saldo inicial R$ {Decimal(str(current['initial_balance'])):.2f}".replace('.', ',')
            if opened else 'Caixa fechado · informe o saldo inicial para começar.'
        )
        self.open_form.setVisible(not opened)
        self.close_form.setVisible(opened)
        self.action_button.setText('Fechar caixa' if opened else 'Iniciar caixa')
        self.action_button.setEnabled(True)
        self.feedback.clear()
        self.adjustSize()

    def submit(self):
        if self.current:
            values = {key: Decimal(str(field.value())) for key, field in self.declared.items()}
            reason = self.justification.text()
            log_id = self.current['id']
            self._run(lambda: self.service.close(values, reason, register_log_id=log_id), self._closed)
        else:
            balance = Decimal(str(self.initial_balance.value()))
            self._run(lambda: self.service.open(balance), self._opened)

    def _opened(self, result):
        self._loaded(result)
        for field in self.declared.values():
            field.setValue(0)
        self.justification.clear()
        self.feedback.setText('Caixa iniciado. As novas vendas serão vinculadas a esta sessão.')

    def _closed(self, result):
        self._loaded(None)
        self.feedback.setText(
            f"Caixa fechado. Esperado: R$ {Decimal(str(result['total_expected'])):.2f} · "
            f"Declarado: R$ {Decimal(str(result['total_declared'])):.2f} · "
            f"Diferença: R$ {Decimal(str(result['difference'])):.2f}".replace('.', ',')
        )
