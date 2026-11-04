"""Aceite adicional da revisão de 2026-11-03; falhas documentam bugs abertos.

Executar separadamente: PYTHONPATH=src QT_QPA_PLATFORM=offscreen
.venv/bin/python -m pytest docs/auditoria/2026-11-03/test_demo_review.py -q
Não desabilita nem modifica testes existentes ou código de produção.
"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from stockflow.application.dto.sale_filter import SaleFilter
from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.sale_receipt import ReceiptCompany, ReceiptNotAvailable, build_sale_receipt
from stockflow.presentation import backend, demo_accounts, demo_status
from stockflow.presentation.app import LoginFlow


@pytest.fixture
def demo(monkeypatch, tmp_path):
    monkeypatch.setenv('STOCKFLOW_BACKEND', 'demo')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    monkeypatch.setattr(backend, '_demo_users', {})
    monkeypatch.setattr(demo_accounts, 'DEMO_ACCOUNTS_BY_EMAIL', dict(demo_accounts.DEMO_ACCOUNTS_BY_EMAIL))
    monkeypatch.setattr(demo_status, '_ACTIVE_BY_USER_ID', {})
    def forbidden(*args, **kwargs):
        pytest.fail('Modo demo tentou conectar ao Supabase')
    monkeypatch.setattr(backend, '_client', forbidden)
    messages = []
    for method in ('critical', 'warning', 'information'):
        monkeypatch.setattr(QMessageBox, method, lambda *args, **kwargs: messages.append(args[1:]))
    app = QApplication.instance() or QApplication([])
    flow = LoginFlow(QSettings(str(tmp_path / 'login.ini'), QSettings.IniFormat))
    flow.login.demo_button.click()
    assert flow.main is not None, messages
    window = flow.main
    window.review_messages = messages
    yield window
    if flow.main is not None:
        flow.main.close()
    flow.login.close()
    app.processEvents()


def sell(window, codes=('PRD-009',), quantity=1):
    if window.cash_register_service.current() is None:
        window.cash_register_service.open(0)
    client = next(c for c in window.client_repository.list_all() if c.active)
    return window.sale_service.register_multiple(
        window.session, client.client_id,
        tuple(SaleItemInput(code, quantity) for code in codes), payment_method='PIX',
    )


def test_failed_multi_item_return_is_atomic(demo):
    sale = sell(demo, ('PRD-009', 'PRD-008'))
    demo.product_repository.set_active('PRD-008', False)
    stock_before = {code: p.stock for code, p in demo.products.items()}
    movements_before = deepcopy(demo.movement_repository.list_movements())
    demo._devolver_venda(sale['id'], 'Devolução de dois itens')
    assert demo.review_messages, 'O segundo item inativo deve produzir a recusa observada'
    assert demo.sale_repository.get(sale['id'])['status'] == 'CONCLUIDA'
    assert {code: p.stock for code, p in demo.products.items()} == stock_before
    assert demo.movement_repository.list_movements() == movements_before


def test_cancelled_sale_cannot_return_items_again(demo):
    # Isola o contrato do repositório US20 com empresa válida. O login demo
    # não fornece company_id; este teste não representa aceite da UI US20.
    demo.session = replace(demo.session, company_id=str(uuid4()))
    demo.sale_repository._session = demo.session
    sale = sell(demo)
    demo.sale_service.cancel_sale(demo.session, sale['id'], 'Cancelamento antes da entrega')
    with pytest.raises(ValueError):
        demo.sale_repository.partial_return(
            sale['id'], [{'sale_item_id': sale['items'][0]['id'], 'quantity': 1}],
            'Nova tentativa de devolver a mesma unidade', str(uuid4()),
        )


def test_closed_register_sale_cannot_be_changed(demo):
    sale = sell(demo)
    demo.cash_register_service.close({'pix': Decimal(sale['total'])}, '')
    with pytest.raises(ValueError):
        demo.sale_service.cancel_sale(demo.session, sale['id'], 'Cancelamento após conferência')


def test_created_product_stock_has_confirmed_movement(demo):
    demo.estoque_page.new_product_button.click()
    page = demo.novo_produto_page
    page.name_input.setText('Produto da auditoria')
    page.category_input.setCurrentText('Eletrônicos')
    page.sale_price_input.setValue(20)
    page.initial_stock_input.setValue(7)
    code = page.code_input.text()  # gerado pelo aplicativo, não pelo teste
    page.save_button.click()
    assert demo.last_save_error is None, demo.review_messages
    assert int(demo.products[code].stock) == 7
    rows = demo.movement_repository.list_movements(code)
    balance = sum((1 if row[3] == 'Entrada' else -1) * row[4]
                  for row in rows if row[5] == 'Confirmada')
    assert balance == 7, rows


def test_product_edit_does_not_erase_a_sale_made_after_form_opened(demo):
    code = 'PRD-009'
    demo.estoque_page.stock_table.edit_buttons[0].click()
    page = demo.editar_produto_page
    assert page.code_input.text() == code
    sell(demo, (code,))
    stock_after_sale = demo.products[code].stock
    page.name_input.setText('Monitor com nome revisado')
    page.save_button.click()
    assert demo.last_save_error is None
    assert demo.products[code].stock == stock_after_sale


def test_edited_user_status_matches_authentication(demo):
    account = demo_accounts.conta_por_papel(UserRole.SELLER)
    backend.save_user(demo.session, user_id=account.user_id, name=account.name,
                      email=account.email, role=account.role, department='Comercial')
    backend.set_user_active(demo.session, account.user_id, False)
    assert demo_accounts.autenticar(account.email, account.password) is None
    row = next(r for r in backend.build_demo_user_directory() if r.user_id == account.user_id)
    assert row[4] == 'Inativo'


def test_last_admin_cannot_demote_itself(demo):
    account = demo_accounts.conta_admin()
    with pytest.raises(ValueError):
        backend.save_user(demo.session, user_id=account.user_id, name=account.name,
                          email=account.email, role=UserRole.SELLER)


def test_same_day_history_uses_time_before_id(demo):
    repo = demo.sale_repository
    repo.rows = [
        {'id': 'aaaaaaaa-0000-0000-0000-000000000001', 'data': '03/11/2026 17:30', 'status': 'CONCLUIDA'},
        {'id': 'ffffffff-0000-0000-0000-000000000002', 'data': '03/11/2026 08:30', 'status': 'CONCLUIDA'},
    ]
    page = repo.list_page(SaleFilter(sort='DATA_DESC'), 1, 20)
    assert page.rows[0]['data'] == '03/11/2026 17:30'


def test_receipt_rejects_total_that_disagrees_with_items(demo):
    sale = sell(demo)
    inconsistent = deepcopy(sale)
    inconsistent['total'] = '0.01'
    with pytest.raises(ReceiptNotAvailable):
        build_sale_receipt(inconsistent, ReceiptCompany('Empresa fictícia'))


def test_all_demo_pages_and_csv_reports_are_available(demo, tmp_path):
    for key, page in demo.page_widgets.items():
        assert demo.show_page(key)
        assert demo.pages.currentWidget() is page
    page = demo.reports_page
    for kind in ('estoque', 'vendas', 'movimentacoes', 'auditoria'):
        page.kind.setCurrentIndex(page.kind.findData(kind))
        page.refresh()
        assert page.rows and not page.error.text(), kind
        target = tmp_path / f'{kind}.csv'
        page.export_csv(target)
        assert target.read_bytes().startswith(b'\xef\xbb\xbf')
        assert len(target.read_text(encoding='utf-8-sig').splitlines()) > 1


def test_open_sale_receipt_close_happy_path(demo):
    sale = sell(demo)
    receipt = demo.receipt_service.issue(demo.session, sale['id'])
    assert receipt.net == Decimal(sale['total'])
    result = demo.cash_register_service.close({'pix': receipt.net}, '')
    assert result['total_sales'] == receipt.net
    assert result['difference'] == 0
    assert demo.cash_register_service.current() is None
