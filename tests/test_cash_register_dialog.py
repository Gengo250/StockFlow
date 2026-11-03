from decimal import Decimal
from types import SimpleNamespace

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
    dialog.declared['dinheiro'].setValue(90)
    dialog.action_button.click()
    assert 'justificativa' in dialog.feedback.text()
    assert dialog.declared['dinheiro'].value() == 90
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
