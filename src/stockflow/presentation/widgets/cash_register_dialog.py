"""Abertura e conferência do caixa sem bloquear a interface durante I/O."""
from decimal import Decimal

from PySide6.QtCore import QLocale, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractSpinBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)
from stockflow.application.services.cash_register_service import PAYMENT_LABELS
from stockflow.presentation.styles import design_system as ds
from stockflow.presentation.workers import executar_agora


def _currency(value):
    return 'R$ ' + format(Decimal(str(value)), ',.2f').translate(str.maketrans('.,', ',.'))


class CashRegisterDialog(QDialog):
    def __init__(self, service, parent=None, execute=executar_agora):
        super().__init__(parent)
        self.service, self.execute = service, execute
        self.current = None
        self._busy = False
        self._state_known = False
        self._follow_feedback = False
        self.setWindowTitle('Caixa')
        self.setObjectName('cashRegisterDialog')
        self.setStyleSheet(ds.page_qss('cashRegisterDialog', 'cashRegisterContent')
                          + ds.field_qss() + ds.button_qss())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # O formulário pode crescer com a fonte e as mensagens. Só o conteúdo
        # rola; a janela e as ações não saltam a cada abertura/fechamento.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('cashRegisterContent')
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(16)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)
        self.status = QLabel('Consulte a situação do seu caixa.')
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        content_layout.addWidget(self.status)
        self.open_form = QWidget()
        form = self._form(self.open_form)
        self.initial_balance = self._amount()
        self._add_row(form, 'Saldo inicial / troco', self.initial_balance)
        content_layout.addWidget(self.open_form)
        self.close_form = QWidget()
        form = self._form(self.close_form)
        self.declared = {}
        for key, label in PAYMENT_LABELS.items():
            self.declared[key] = self._amount()
            self._add_row(form, label, self.declared[key])
        self.justification = QLineEdit()
        self.justification.setPlaceholderText('Obrigatória quando houver diferença')
        self.justification.setMaxLength(2000)
        self.justification.setMinimumHeight(ds.CONTROL_HEIGHT)
        self._add_row(form, 'Justificativa', self.justification)
        content_layout.addWidget(self.close_form)
        self.close_form.hide()
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(Qt.PlainText)
        self.feedback.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        content_layout.addWidget(self.feedback)
        content_layout.addStretch()
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._reveal_feedback)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._queue_feedback)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton('Atualizar')
        self.action_button = QPushButton('Iniciar caixa')
        self.action_button.setStyleSheet(ds.button_qss(primary=True))
        self.action_button.setEnabled(False)
        self.dismiss_button = QPushButton('Voltar')
        for button in (self.refresh_button, self.action_button, self.dismiss_button):
            button.setAutoDefault(False)
            button.setMinimumHeight(ds.CONTROL_HEIGHT)
            buttons.addWidget(button)
        self.action_button.setDefault(True)
        layout.addLayout(buttons)
        self.refresh_button.clicked.connect(self.refresh)
        self.action_button.clicked.connect(self.submit)
        self.dismiss_button.clicked.connect(self.reject)

        available = self.screen().availableGeometry()
        width, height = available.width() - 48, available.height() - 48
        self.setMinimumSize(min(480, width), min(280, height))
        self.resize(min(640, width), min(600, height))

    @staticmethod
    def _form(widget):
        form = QFormLayout(widget)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return form

    @staticmethod
    def _add_row(form, text, field):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setBuddy(field)
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        form.addRow(label, field)

    @staticmethod
    def _amount():
        field = QDoubleSpinBox()
        field.setLocale(QLocale('pt_BR'))
        field.setGroupSeparatorShown(True)
        # Deixa o excesso visível para recusá-lo no envio. Limitar a edição ao
        # teto do negócio fazia 100000000 virar 10000000 ao descartar um dígito.
        field.setRange(0, 999999999999.99)
        field.setToolTip('Valor máximo permitido por campo: R$ 99.999.999,99.')
        field.setDecimals(2)
        field.setPrefix('R$ ')
        field.setButtonSymbols(QAbstractSpinBox.NoButtons)
        field.setMinimumHeight(ds.CONTROL_HEIGHT)
        return field

    def reject(self):
        if not self._busy:
            super().reject()

    def _run(self, operation, success):
        if self._busy:
            return
        self._feedback_timer.stop()
        self._follow_feedback = False
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
            self._follow_feedback = True
            self._feedback_timer.start(0)

        self.execute(operation, loaded, failed)

    def _queue_feedback(self):
        if self._follow_feedback and self.feedback.text() and not self._busy:
            self._feedback_timer.start(0)

    def _reveal_feedback(self):
        # A quebra de linhas pode mudar o alcance da barra depois do primeiro
        # layout. rangeChanged refaz a revelação usando a geometria definitiva.
        if self.feedback.text():
            self.scroll.ensureWidgetVisible(self.feedback, 0, 12)

    def refresh(self):
        self._state_known = False
        self._run(self.service.current, self._loaded)

    def _loaded(self, current):
        self._feedback_timer.stop()
        self._follow_feedback = False
        self.current = current
        self._state_known = True
        opened = bool(current)
        self.status.setText(
            f"Caixa aberto · saldo inicial {_currency(current['initial_balance'])}"
            if opened else 'Caixa fechado · informe o saldo inicial para começar.'
        )
        self.open_form.setVisible(not opened)
        self.close_form.setVisible(opened)
        self.action_button.setText('Fechar caixa' if opened else 'Iniciar caixa')
        self.action_button.setEnabled(True)
        self.feedback.clear()

    def submit(self):
        if self._busy or not self._state_known:
            return
        fields = self.declared.values() if self.current else (self.initial_balance,)
        if any(Decimal(str(field.value())) > Decimal('99999999.99') for field in fields):
            self.feedback.setText('O valor máximo permitido por campo é R$ 99.999.999,99.')
            self._follow_feedback = True
            self._feedback_timer.start(0)
            return
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
            f"Caixa fechado. Esperado: {_currency(result['total_expected'])} · "
            f"Declarado: {_currency(result['total_declared'])} · "
            f"Diferença: {_currency(result['difference'])}"
        )
        self._follow_feedback = True
        self._feedback_timer.start(0)
