from decimal import Decimal
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QScrollArea

from stockflow.application.services.cash_register_service import CashRegisterService
from stockflow.infrastructure.repositories.demo_cash_register_repository import DemoCashRegisterRepository
from stockflow.presentation.demo_accounts import conta_admin
from stockflow.presentation.widgets.cash_register_dialog import CashRegisterDialog


def test_dialog_open_close_and_preserves_input_on_failure(qapp):
    service = CashRegisterService(DemoCashRegisterRepository(SimpleNamespace(rows=[])), conta_admin().session())
    dialog = CashRegisterDialog(service)
    dialog.refresh()
    assert dialog.action_button.text() == 'Iniciar caixa'
    dialog.initial_balance.setValue(100)
    dialog.action_button.click()
    assert service.current()['initial_balance'] == Decimal('100')
    assert dialog.action_button.text() == 'Fechar caixa'
    dialog.declared['DINHEIRO'].setValue(90)
    dialog.action_button.click()
    assert 'justificativa' in dialog.feedback.text()
    assert dialog.declared['DINHEIRO'].value() == 90
    assert service.current()
    dialog.justification.setText('Diferença conferida')
    dialog.action_button.click()
    assert service.current() is None
    assert 'fechado' in dialog.feedback.text().lower()
    dialog.close()


def test_dialog_load_error_prevents_write_and_allows_retry(qapp):
    class Offline:
        def current(self):
            raise RuntimeError('Sem conexão')
    dialog = CashRegisterDialog(Offline())
    dialog.refresh()
    assert not dialog.action_button.isEnabled()
    assert dialog.refresh_button.isEnabled()
    assert 'Sem conexão' in dialog.feedback.text()
    dialog.close()


@pytest.fixture
def cash_dialog(qapp):
    service = CashRegisterService(DemoCashRegisterRepository(SimpleNamespace(rows=[])), conta_admin().session())
    dialog = CashRegisterDialog(service)
    dialog.refresh()
    dialog.show()
    qapp.processEvents()
    yield dialog
    dialog.close()


def test_enter_submits_opening_and_closing_instead_of_refreshing(qapp, cash_dialog):
    dialog = cash_dialog
    dialog.initial_balance.setFocus()
    dialog.initial_balance.selectAll()
    QTest.keyClicks(dialog.initial_balance, '100,00')
    QTest.keyClick(dialog.initial_balance, Qt.Key_Return)
    assert dialog.service.current()['initial_balance'] == Decimal('100')
    dialog.declared['DINHEIRO'].setFocus()
    dialog.declared['DINHEIRO'].selectAll()
    QTest.keyClicks(dialog.declared['DINHEIRO'], '100,00')
    QTest.keyClick(dialog.declared['DINHEIRO'], Qt.Key_Return)
    assert dialog.service.current() is None
    assert 'Diferença: R$ 0,00' in dialog.feedback.text()


def test_open_close_refresh_keep_window_and_action_in_place(qapp, cash_dialog):
    dialog = cash_dialog
    size = dialog.size()
    action_rect = dialog.action_button.geometry()
    dialog.initial_balance.setValue(100)
    for _ in range(2):
        dialog.action_button.click()
        qapp.processEvents()
        assert dialog.size() == size
        assert dialog.action_button.geometry() == action_rect
        dialog.refresh_button.click()
        qapp.processEvents()
        assert dialog.size() == size
        dialog.declared['DINHEIRO'].setValue(100)
        dialog.action_button.click()
        qapp.processEvents()
        assert dialog.size() == size
        assert dialog.action_button.geometry() == action_rect
        assert dialog.service.current() is None


def test_validation_feedback_is_visible_in_small_window(qapp, cash_dialog):
    dialog = cash_dialog
    dialog.resize(520, 360)
    dialog.initial_balance.setValue(100)
    dialog.action_button.click()
    qapp.processEvents()
    dialog.declared['DINHEIRO'].setValue(90)
    dialog.action_button.click()
    qapp.processEvents()
    assert 'justificativa' in dialog.feedback.text()
    bounds = QRect(dialog.feedback.mapTo(dialog.scroll.viewport(), QPoint()), dialog.feedback.size())
    assert dialog.scroll.viewport().rect().contains(bounds)
    assert dialog.declared['DINHEIRO'].value() == 90
    assert dialog.service.current()


def test_maximum_amounts_and_long_justification_are_preserved(qapp, cash_dialog):
    dialog = cash_dialog
    dialog.initial_balance.selectAll()
    QTest.keyClicks(dialog.initial_balance, '99999999,99')
    dialog.action_button.click()
    assert dialog.service.current()['initial_balance'] == Decimal('99999999.99')
    for field in dialog.declared.values():
        field.selectAll()
        QTest.keyClicks(field, '99999999,99')
    dialog.action_button.click()
    assert 'justificativa' in dialog.feedback.text()
    assert all(field.value() == 99999999.99 for field in dialog.declared.values())
    reason = ('Conferencia manual dos valores altos e comprovantes de cada pagamento. ' * 40)[:1999] + '.'
    QTest.keyClicks(dialog.justification, reason)
    assert dialog.justification.text() == reason
    dialog.action_button.click()
    assert dialog.service.current() is None
    result = dialog.service.repository.history[-1]
    assert result['total_expected'] == Decimal('99999999.99')
    assert result['total_declared'] == Decimal('599999999.94')
    assert result['difference'] == Decimal('499999999.95')
    assert result['justification'] == reason
    assert 'Declarado: R$ 599.999.999,94' in dialog.feedback.text()
    assert 'Diferença: R$ 499.999.999,95' in dialog.feedback.text()


@pytest.mark.parametrize('amount', ['100000000,00', '1000000000,00', '999999999999,99'])
def test_out_of_range_typing_cannot_open_with_a_silently_smaller_amount(cash_dialog, amount):
    dialog = cash_dialog
    dialog.initial_balance.selectAll()
    QTest.keyClicks(dialog.initial_balance, amount)
    dialog.action_button.click()
    assert dialog.service.current() is None
    assert '99.999.999,99' in dialog.feedback.text()


@pytest.mark.parametrize('payment', ['DINHEIRO', 'DEBITO', 'CREDITO', 'PIX', 'VALE', 'OUTRO'])
def test_excess_in_any_payment_prevents_closing_even_with_a_reason(cash_dialog, payment):
    dialog = cash_dialog
    dialog.action_button.click()
    field = dialog.declared[payment]
    field.selectAll()
    QTest.keyClicks(field, '100000000,00')
    dialog.justification.setText('Conferencia dos valores altos.')
    dialog.action_button.click()
    assert dialog.service.current()
    assert not dialog.service.repository.history
    assert field.value() == 100000000
    assert '99.999.999,99' in dialog.feedback.text()
    assert dialog.justification.text() == 'Conferencia dos valores altos.'


def test_large_labels_and_fields_remain_reachable_in_small_window(qapp):
    original_font = qapp.font()
    dialog = None
    try:
        qapp.setFont(QFont('Sans Serif', 20))
        service = CashRegisterService(DemoCashRegisterRepository(SimpleNamespace(rows=[])), conta_admin().session())
        dialog = CashRegisterDialog(service)
        dialog.refresh()
        dialog.show()
        dialog.action_button.click()
        dialog.resize(520, 360)
        qapp.processEvents()
        assert dialog.width() <= 520
        assert dialog.height() <= 360
        scroll = dialog.findChild(QScrollArea)
        assert scroll is not None, 'O formulário precisa continuar acessível quando não cabe na janela.'
        for label in dialog.close_form.findChildren(QLabel):
            needed = label.fontMetrics().boundingRect(
                QRect(0, 0, label.width(), 10000), Qt.TextWordWrap, label.text()
            )
            assert label.height() >= needed.height(), label.text()
            assert label.width() >= needed.width(), label.text()
        dialog.declared['DINHEIRO'].setFocus(Qt.TabFocusReason)
        for field in (*dialog.declared.values(), dialog.justification):
            qapp.processEvents()
            assert qapp.focusWidget() is field
            bounds = QRect(field.mapTo(scroll.viewport(), QPoint()), field.size())
            assert scroll.viewport().rect().contains(bounds), (field, bounds)
            QTest.keyClick(field, Qt.Key_Tab)
        for button in (dialog.refresh_button, dialog.action_button, dialog.dismiss_button):
            assert dialog.rect().contains(button.geometry())
        # A mensagem cresce ao quebrar linhas com fonte ampliada. A rolagem
        # deve acompanhar o layout final, não a altura anterior do QLabel.
        dialog.declared['DINHEIRO'].setValue(1)
        dialog.action_button.click()
        QTest.qWait(50)
        assert 'justificativa' in dialog.feedback.text()
        bounds = QRect(dialog.feedback.mapTo(scroll.viewport(), QPoint()), dialog.feedback.size())
        assert scroll.viewport().rect().contains(bounds)
    finally:
        if dialog is not None:
            dialog.close()
        qapp.setFont(original_font)
