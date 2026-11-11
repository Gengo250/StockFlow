"""Abertura e conferência do caixa sem bloquear a interface durante I/O."""
from decimal import Decimal

from PySide6.QtCore import QEvent, QLocale, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractSpinBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)
from stockflow.application.services.cash_register_service import PAYMENT_LABELS, closing_summary
from stockflow.presentation.styles import design_system as ds
from stockflow.presentation.workers import executar_agora

# Nome curto de cada forma de pagamento, sem a instrução do campo declarado.
PAYMENT_NAMES = {key: label.split(' (')[0] for key, label in PAYMENT_LABELS.items()}


def _currency(value):
    return 'R$ ' + format(Decimal(str(value)), ',.2f').translate(str.maketrans('.,', ',.'))


def _breakdown(totals):
    """Resumo em uma linha das formas de pagamento com movimento."""
    parts = [f'{PAYMENT_NAMES[key]} {_currency(totals.get(key, 0))}'
             for key in PAYMENT_LABELS if Decimal(str(totals.get(key, 0)))]
    return ' · '.join(parts) or 'nenhuma venda concluída'


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
        close_layout = QVBoxLayout(self.close_form)
        close_layout.setContentsMargins(0, 0, 0, 0)
        close_layout.setSpacing(16)
        # Totais calculados pelo sistema: soma por forma de pagamento e total
        # dos totais, vindos de fn_register_session_summary.
        self.summary_box = QWidget()
        self.summary_box.setObjectName('cashRegisterSummary')
        summary_layout = QVBoxLayout(self.summary_box)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(8)
        summary_title = QLabel('Calculado pelo sistema (vendas concluídas)')
        summary_title.setWordWrap(True)
        summary_title.setStyleSheet('font-weight: 600;')
        summary_layout.addWidget(summary_title)
        summary_form = QWidget()
        form = self._form(summary_form)
        self.expected_labels = {}
        for key in PAYMENT_LABELS:
            self.expected_labels[key] = self._value_label()
            self._add_row(form, PAYMENT_NAMES[key], self.expected_labels[key])
        self.total_sales_label = self._value_label(bold=True)
        self._add_row(form, 'Total das vendas', self.total_sales_label)
        self.expected_dinheiro_label = self._value_label()
        self._add_row(form, 'Dinheiro esperado na gaveta (com saldo inicial)', self.expected_dinheiro_label)
        self.total_expected_label = self._value_label(bold=True)
        self._add_row(form, 'Total esperado no caixa', self.total_expected_label)
        summary_layout.addWidget(summary_form)
        self.summary_error = QLabel()
        self.summary_error.setWordWrap(True)
        self.summary_error.setTextFormat(Qt.PlainText)
        self.summary_error.hide()
        summary_layout.addWidget(self.summary_error)
        self.fill_button = QPushButton('Preencher com os valores calculados')
        self.fill_button.setAutoDefault(False)
        self.fill_button.setMinimumHeight(ds.CONTROL_HEIGHT)
        self.fill_button.setEnabled(False)
        self.fill_button.clicked.connect(self.fill_declared)
        summary_layout.addWidget(self.fill_button)
        close_layout.addWidget(self.summary_box)
        declared_title = QLabel('Valores conferidos')
        declared_title.setWordWrap(True)
        declared_title.setStyleSheet('font-weight: 600;')
        close_layout.addWidget(declared_title)
        declared_form = QWidget()
        form = self._form(declared_form)
        close_layout.addWidget(declared_form)
        self.summary = None
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
        self._focus_timer = QTimer(self)
        self._focus_timer.setSingleShot(True)
        self._focus_timer.timeout.connect(self._reveal_focused_field)
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

        # O editor interno do spinbox também pode receber foco por teclado.
        for field in (self.initial_balance, *self.declared.values(), self.justification):
            field.installEventFilter(self)
            if isinstance(field, QDoubleSpinBox):
                field.lineEdit().installEventFilter(self)

        available = self.screen().availableGeometry()
        width, height = available.width() - 48, available.height() - 48
        self.setMinimumSize(min(480, width), min(280, height))
        self.resize(min(640, width), min(600, height))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.FocusIn:
            self._feedback_timer.stop()
            self._follow_feedback = False
            self._focus_timer.start(0)
        return super().eventFilter(watched, event)

    def _reveal_focused_field(self):
        field = self.focusWidget()
        if field is None or not self.scroll.widget().isAncestorOf(field):
            return
        if isinstance(field.parentWidget(), QDoubleSpinBox):
            field = field.parentWidget()
        # ensureWidgetVisible usa o editor interno como retângulo de foco.
        # Revelar o controle inteiro evita cortar a borda inferior do spinbox.
        center = field.mapTo(self.scroll.widget(), field.rect().center())
        self.scroll.ensureVisible(
            center.x(), center.y(), field.width() // 2, field.height() // 2 + 12,
        )

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
    def _value_label(bold=False):
        label = QLabel('—')
        label.setTextFormat(Qt.PlainText)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setMinimumHeight(ds.CONTROL_HEIGHT)
        if bold:
            label.setStyleSheet('font-weight: 600;')
        return label

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
        if opened:
            self._load_summary()

    def _load_summary(self):
        self.fill_button.setEnabled(False)
        self.summary_error.hide()
        for label in self.expected_labels.values():
            label.setText('…')
        self.total_sales_label.setText('…')
        self.expected_dinheiro_label.setText('…')
        self.total_expected_label.setText('…')
        log_id = self.current['id'] if self.current else None

        def fetch():
            if hasattr(self.service, 'summary'):
                return self.service.summary(register_log_id=log_id)
            return None

        def loaded(summary):
            self.summary = summary
            if not summary:
                return
            totals = summary.get('totals', {})
            for key, label in self.expected_labels.items():
                label.setText(_currency(totals.get(key, 0)))
            self.total_sales_label.setText(_currency(summary.get('total_sales', 0)))
            self.expected_dinheiro_label.setText(_currency(summary.get('expected_dinheiro', 0)))
            self.total_expected_label.setText(_currency(summary.get('total_expected', 0)))
            self.fill_button.setEnabled(True)

        def failed(err):
            self.summary_error.setText(f"Não foi possível carregar os totais calculados: {err}")
            self.summary_error.show()

        self.execute(fetch, loaded, failed)

    def fill_declared(self):
        if not self.summary:
            return
        totals = self.summary.get('totals', {})
        for key, field in self.declared.items():
            if key == 'DINHEIRO':
                val = self.summary.get('expected_dinheiro', totals.get(key, 0))
            else:
                val = totals.get(key, 0)
            field.setValue(float(val))

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
        totals = result.get('totals') or {}
        breakdown_text = f" ({_breakdown(totals)})" if totals else ""
        self.feedback.setText(
            f"Caixa fechado. Esperado: {_currency(result['total_expected'])}{breakdown_text} · "
            f"Declarado: {_currency(result['total_declared'])} · "
            f"Diferença: {_currency(result['difference'])}"
        )
        self._follow_feedback = True
        self._feedback_timer.start(0)
