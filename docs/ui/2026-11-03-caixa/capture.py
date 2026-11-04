"""Aceite visual do caixa demo; capturas somente das janelas deste processo.

Da raiz: PYTHONPATH=src .venv/bin/python docs/ui/2026-11-03-caixa/capture.py
Use QT_QPA_PLATFORM=offscreen para repetir sem servidor gráfico.
"""
import json
import os
from decimal import Decimal
from pathlib import Path
import socket
import sys
import tempfile
import traceback

os.environ['STOCKFLOW_BACKEND'] = 'demo'
scratch = tempfile.TemporaryDirectory(prefix='stockflow-cash-visual-')
os.environ['XDG_CONFIG_HOME'] = str(Path(scratch.name) / 'config')
os.environ['XDG_CACHE_HOME'] = str(Path(scratch.name) / 'cache')

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from stockflow.presentation.app import LoginFlow
from stockflow.presentation.widgets.cash_register_dialog import CashRegisterDialog

network_attempts = []


def forbid_network(*args, **kwargs):
    network_attempts.append(True)
    raise AssertionError('O aceite do demo não deve acessar a rede.')


socket.socket.connect = forbid_network
socket.create_connection = forbid_network
app = QApplication([])
output = Path(__file__).parent / app.platformName()
output.mkdir(parents=True, exist_ok=True)
report = {'platform': app.platformName(), 'style': app.style().objectName(), 'states': []}
flow = LoginFlow()
flow.login.show()
dialog = None
initial_size = None
initial_button = None


def capture(name):
    app.processEvents()
    dialog.grab().save(str(output / f'{name}.png'))
    report['states'].append({
        'name': name, 'size': dialog.size().toTuple(),
        'action': dialog.action_button.geometry().getRect(),
        'status': dialog.status.text(), 'feedback': dialog.feedback.text(),
    })


def enter():
    flow.login.demo_button.click()
    assert flow.main is not None
    flow.main.show_page('vendas')
    # O botão abre o mesmo diálogo modal usado em produção.
    QTimer.singleShot(100, opening)
    flow.main.vendas_page.cash_register_button.click()


def opening():
    global dialog, initial_size, initial_button
    dialog = app.activeModalWidget()
    assert isinstance(dialog, CashRegisterDialog)
    initial_size = dialog.size()
    initial_button = dialog.action_button.geometry()
    capture('01-abertura')
    dialog.initial_balance.setFocus()
    dialog.initial_balance.selectAll()
    QTest.keyClicks(dialog.initial_balance, '100,00')
    QTest.keyClick(dialog.initial_balance, Qt.Key_Return)
    QTimer.singleShot(200, opened)


def opened():
    assert flow.main.cash_register_service.current()['initial_balance'] == 100
    assert dialog.size() == initial_size
    assert dialog.action_button.geometry() == initial_button
    capture('02-aberto')
    # Alternar hover/foco não deve deslocar a ação.
    for _ in range(4):
        QTest.mouseMove(dialog, QPoint(2, 2))
        QTest.mouseMove(dialog.action_button, dialog.action_button.rect().center())
        app.processEvents()
        assert dialog.action_button.geometry() == initial_button
    dialog.action_button.click()
    QTimer.singleShot(200, invalid_count)


def invalid_count():
    assert 'justificativa' in dialog.feedback.text()
    assert flow.main.cash_register_service.current()
    capture('03-divergencia')
    dialog.declared['dinheiro'].setValue(100)
    dialog.action_button.click()
    QTimer.singleShot(200, closed)


def closed():
    assert flow.main.cash_register_service.current() is None
    assert 'Diferença: R$ 0,00' in dialog.feedback.text()
    assert dialog.size() == initial_size
    assert dialog.action_button.geometry() == initial_button
    capture('04-fechado')
    dialog.action_button.click()
    QTimer.singleShot(200, reopened)


def reopened():
    assert flow.main.cash_register_service.current()
    assert all(field.value() == 0 for field in dialog.declared.values())
    capture('05-reaberto')
    dialog.close()
    # Nova janela lê o mesmo caixa aberto, agora sob fonte ampliada.
    app.setFont(QFont('Sans Serif', 20))
    QTimer.singleShot(100, compact)
    flow.main.vendas_page.cash_register_button.click()


def compact():
    global dialog
    dialog = app.activeModalWidget()
    assert isinstance(dialog, CashRegisterDialog)
    dialog.resize(520, 360)
    QTimer.singleShot(200, compact_ready)


def compact_ready():
    assert dialog.width() <= 520 and dialog.height() <= 360
    capture('06-fonte-ampliada')
    for label in dialog.close_form.findChildren(QLabel):
        needed = label.fontMetrics().boundingRect(
            QRect(0, 0, label.width(), 10000), Qt.TextWordWrap, label.text()
        )
        assert label.width() >= needed.width() and label.height() >= needed.height(), label.text()
    dialog.declared['dinheiro'].setFocus(Qt.TabFocusReason)
    for field in (*dialog.declared.values(), dialog.justification):
        app.processEvents()
        assert app.focusWidget() is field
        bounds = QRect(field.mapTo(dialog.scroll.viewport(), QPoint()), field.size())
        assert dialog.scroll.viewport().rect().contains(bounds), bounds
        QTest.keyClick(field, Qt.Key_Tab)
    capture('07-ultimo-campo')
    dialog.action_button.click()
    QTimer.singleShot(200, compact_error)


def compact_error():
    assert 'justificativa' in dialog.feedback.text()
    bounds = QRect(dialog.feedback.mapTo(dialog.scroll.viewport(), QPoint()), dialog.feedback.size())
    capture('08-erro-visivel')
    assert dialog.scroll.viewport().rect().contains(bounds), (bounds, dialog.scroll.viewport().rect(), dialog.scroll.verticalScrollBar().value(), dialog.scroll.verticalScrollBar().maximum())
    dialog.justification.setText('Encerramento do cenario de navegacao.')
    dialog.action_button.click()
    QTimer.singleShot(200, high_open)


def high_open():
    assert flow.main.cash_register_service.current() is None
    dialog.initial_balance.selectAll()
    QTest.keyClicks(dialog.initial_balance, '100000000,00')
    dialog.action_button.click()
    assert flow.main.cash_register_service.current() is None
    assert dialog.initial_balance.value() == 100000000
    assert '99.999.999,99' in dialog.feedback.text()
    QTimer.singleShot(200, high_limit)


def high_limit():
    capture('09-acima-do-limite')
    dialog.initial_balance.selectAll()
    QTest.keyClicks(dialog.initial_balance, '99999999,99')
    dialog.action_button.click()
    assert flow.main.cash_register_service.current()['initial_balance'] == Decimal('99999999.99')
    for field in dialog.declared.values():
        field.selectAll()
        QTest.keyClicks(field, '99999999,99')
    # O excesso em qualquer pagamento também deve ser recusado com justificativa.
    dialog.declared['pix'].selectAll()
    QTest.keyClicks(dialog.declared['pix'], '100000000,00')
    dialog.justification.setText('Conferencia dos valores altos.')
    dialog.action_button.click()
    assert flow.main.cash_register_service.current()
    assert '99.999.999,99' in dialog.feedback.text()
    dialog.declared['pix'].selectAll()
    QTest.keyClicks(dialog.declared['pix'], '99999999,99')
    reason = ('Conferencia manual dos valores altos e comprovantes de cada pagamento. ' * 40)[:1999] + '.'
    dialog.justification.setText(reason)
    dialog.justification.setCursorPosition(0)
    dialog.scroll.ensureWidgetVisible(dialog.declared['dinheiro'])
    QTimer.singleShot(200, high_fields)


def high_fields():
    capture('10-valores-maximos')
    for field in dialog.declared.values():
        assert field.value() == 99999999.99
        assert field.lineEdit().width() >= field.lineEdit().fontMetrics().horizontalAdvance(field.text()) + 8
    dialog.scroll.ensureWidgetVisible(dialog.justification)
    QTimer.singleShot(200, high_reason)


def high_reason():
    capture('11-justificativa-longa')
    assert len(dialog.justification.text()) == 2000
    report['high_amounts'] = {'reason_length': len(dialog.justification.text())}
    dialog.action_button.click()
    QTimer.singleShot(200, high_closed)


def high_closed():
    assert flow.main.cash_register_service.current() is None
    result = flow.main.cash_register_service.repository.history[-1]
    assert result['total_expected'] == Decimal('99999999.99')
    assert result['total_declared'] == Decimal('599999999.94')
    assert result['difference'] == Decimal('499999999.95')
    assert len(result['justification']) == 2000
    report['high_amounts'].update({key: str(result[key]) for key in ('total_expected', 'total_declared', 'difference')})
    bounds = QRect(dialog.feedback.mapTo(dialog.scroll.viewport(), QPoint()), dialog.feedback.size())
    capture('12-fechamento-valores-altos')
    assert dialog.scroll.viewport().rect().contains(bounds), bounds
    assert not network_attempts and 'supabase' not in sys.modules
    report.update(passed=True, network_attempts=0, supabase_imported=False)
    finish()


def finish():
    (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if dialog:
        dialog.close()
    if flow.main:
        flow.main.close()
    flow.login.close()
    app.quit()


def fail(exc_type, exc_value, tb):
    report.update(passed=False, error=''.join(traceback.format_exception(exc_type, exc_value, tb)))
    finish()


sys.excepthook = fail
QTimer.singleShot(200, enter)
QTimer.singleShot(20000, lambda: (report.update(passed=False, error='Timeout'), finish()))
app.exec()
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report.get('passed') else 1)
