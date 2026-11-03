from decimal import Decimal
from types import SimpleNamespace

import pytest

from stockflow.application.services.cash_register_service import CashRegisterService
from stockflow.infrastructure.repositories.demo_cash_register_repository import DemoCashRegisterRepository
from stockflow.presentation.demo_accounts import conta_admin


def make_service():
    sales = SimpleNamespace(rows=[])
    repo = DemoCashRegisterRepository(sales)
    return CashRegisterService(repo, conta_admin().session()), sales


def test_open_close_includes_sales_and_initial_balance():
    service, sales = make_service()
    opened = service.open(Decimal('100'))
    sales.rows.append(dict(register_log_id=opened['id'], status='CONCLUIDA', total='20', payment_method='PIX'))
    result = service.close({'dinheiro': Decimal('100'), 'pix': Decimal('20')}, '')
    assert result['total_expected'] == 120
    assert result['difference'] == 0
    assert service.current() is None


def test_difference_requires_reason_and_does_not_close():
    service, _ = make_service()
    service.open(Decimal('100'))
    with pytest.raises(ValueError, match='justificativa'):
        service.close({}, '')
    assert service.current()['initial_balance'] == 100
    assert service.close({}, 'Falta conferida')['difference'] == -100


def test_cannot_open_twice_or_close_twice():
    service, _ = make_service()
    service.open(0)
    with pytest.raises(ValueError):
        service.open(0)
    service.close({}, '')
    with pytest.raises(ValueError):
        service.close({}, '')


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', '0.001'])
def test_invalid_money(value):
    service, _ = make_service()
    with pytest.raises(ValueError):
        service.open(Decimal(value))
    assert service.current() is None


def test_requires_sales_permission():
    service, _ = make_service()
    service.session = None
    with pytest.raises(PermissionError):
        service.open(0)


def test_window_wires_cash_register_to_sales(qapp):
    from stockflow.presentation.windows.main_window import MainWindow
    window = MainWindow(conta_admin().session())
    assert window.vendas_page.cash_register_button.isEnabled()
    assert window.sale_repository.cash_register is window.cash_register_service.repository
    with pytest.raises(ValueError, match='Inicie o caixa'):
        window.sale_repository.register_multiple(None, (), Decimal(0))
    window.close()


def test_stale_dialog_cannot_close_replacement_session():
    service, _ = make_service()
    first = service.open(0)
    service.close({}, '')
    second = service.open(0)
    with pytest.raises(ValueError, match='sessão'):
        service.close({}, 'Contagem antiga', register_log_id=first['id'])
    assert service.current()['id'] == second['id']


def test_demo_sale_is_counted_only_in_its_register(qapp):
    from stockflow.application.dto.sale_item import SaleItemInput
    from stockflow.presentation.windows.main_window import MainWindow
    window = MainWindow(conta_admin().session())
    opened = window.cash_register_service.open(Decimal('50'))
    client = next(c for c in window.client_repository.list_all() if c.active)
    code = next(code for code, product in window.products.items() if product.active and int(product.stock) > 0)
    row = window.sale_service.register_multiple(window.session, client.client_id, (SaleItemInput(code, 1),), payment_method='PIX')
    assert row['register_log_id'] == opened['id']
    result = window.cash_register_service.close({'dinheiro': Decimal('50'), 'pix': Decimal(row['total'])}, '')
    assert result['difference'] == 0
    assert result['total_sales'] == Decimal(row['total'])
    window.close()


def test_remote_close_uses_displayed_id_without_selecting_another_session():
    from unittest.mock import Mock
    from uuid import uuid4
    from stockflow.infrastructure.repositories.supabase_cash_register_repository import SupabaseCashRegisterRepository
    client = Mock()
    client.rpc.return_value.execute.return_value.data = {'status': 'CLOSED'}
    repo = SupabaseCashRegisterRepository(client, uuid4())
    displayed = str(uuid4())
    repo.close({}, 'Conferido', register_log_id=displayed)
    assert client.rpc.call_count == 1
    name, payload = client.rpc.call_args.args
    assert name == 'fn_close_register_session'
    assert payload['p_register_log_id'] == displayed
