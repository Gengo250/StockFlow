from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QLabel, QPushButton

from stockflow.domain.enums.price_edit_field import PriceEditField
from stockflow.presentation.pages.historico_precos import HistoricoPrecosPage


def event(day=6, user='Ana', field=PriceEditField.SELL_PRICE, **extra):
    return SimpleNamespace(changed_on=datetime(2026, 11, day, 15, tzinfo=timezone.utc),
                           product_code='P1', product_name='Produto teste', field=field,
                           old_price=None, new_price=Decimal('0'), changed_by=user, **extra)


@pytest.fixture
def page(qapp):
    p = HistoricoPrecosPage()
    p.apply_session(SimpleNamespace(role='ADMIN'))
    yield p
    p.close()


def test_filters_combine_and_dates_are_inclusive(page):
    page.carregar([event(5), event(6), event(6, 'Bia'), event(6, field=PriceEditField.BUY_PRICE)])
    page.usuario_combo.setCurrentIndex(page.usuario_combo.findData('Ana'))
    page.acao_combo.setCurrentIndex(page.acao_combo.findData(PriceEditField.SELL_PRICE))
    page.entidade_combo.setCurrentIndex(1)
    page.data_inicio.setDate(QDate(2026, 11, 6))
    page.data_fim.setDate(QDate(2026, 11, 6))
    page.periodo_check.setChecked(True)
    assert page.table.rowCount() == 1
    assert page.table.item(0, 5).text() == 'Ana'
    assert page.table.item(0, 2).text() == 'Venda'
    page.data_inicio.setDate(QDate(2026, 11, 7))
    assert page.table.rowCount() == 0
    assert not page.aviso_label.isHidden()
    assert not page.details_button.isEnabled()


def test_sort_and_detail_match_selected_row_without_sensitive_payload(page):
    page.carregar([event(4), event(6, token='secret-token', password='secret-password')])
    assert page.table.item(0, 0).text().startswith('06/11/2026')
    page.table.selectRow(0)
    page.details_button.click()
    dialog = page.detail_dialog
    texts = '\n'.join(label.text() for label in dialog.findChildren(QLabel))
    assert 'Ana' in texts and 'Produto teste' in texts
    assert 'Não informado' in texts and 'R$ 0,00' in texts
    assert 'secret' not in texts
    assert all(label.textFormat() == Qt.PlainText for label in dialog.findChildren(QLabel))
    assert [b.text() for b in dialog.findChildren(QPushButton)] == ['Voltar ao histórico']
    dialog.close()
    assert page.table.currentRow() == 0


@pytest.mark.parametrize('role', ['STOCK', 'SELLER', None])
def test_session_change_clears_records_and_open_detail(page, role):
    page.carregar([event()])
    page.table.selectRow(0)
    page.details_button.click()
    dialog = page.detail_dialog
    page.apply_session(SimpleNamespace(role=role))
    page.carregar([event()])
    page.abrir_detalhes()
    assert not dialog.isVisible()
    assert page.table.rowCount() == 0
    assert not page.details_button.isEnabled()


def test_same_role_new_session_also_discards_previous_company(page):
    page.carregar([event()])
    page.apply_session(SimpleNamespace(role='ADMIN'))
    assert page.table.rowCount() == 0
    assert page.usuario_combo.count() == 1


def test_direct_dialog_creation_requires_permission(qapp):
    from stockflow.presentation.dialogs.audit_event_dialog import AuditEventDialog
    from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
    with pytest.raises(PermissionDeniedError):
        AuditEventDialog(event(), SimpleNamespace(role='SELLER'))


def test_unknown_date_last_and_missing_values_are_not_zero(page):
    missing = event()
    missing.changed_on = None
    missing.changed_by = ''
    missing.product_code = ''
    missing.product_name = ''
    missing.new_price = None
    page.carregar([missing, event()])
    assert page.table.item(1, 0).text() == '—'
    page.table.selectRow(1)
    page.details_button.click()
    texts = '\n'.join(label.text() for label in page.detail_dialog.findChildren(QLabel))
    assert 'Produto não disponível' in texts
    assert texts.count('Não informado') == 4
    assert 'R$' not in texts


def test_old_async_result_does_not_repopulate_new_session(qapp, monkeypatch):
    from stockflow.presentation.windows import main_window as module
    from stockflow.presentation.demo_accounts import conta_admin
    monkeypatch.setenv('STOCKFLOW_BACKEND', 'demo')
    monkeypatch.setattr(module, 'using_supabase', lambda: True)
    monkeypatch.setattr(module, 'executar_em_segundo_plano', lambda *job: None)
    window = module.MainWindow(conta_admin().session())
    callbacks = []
    monkeypatch.setattr(window, '_load', lambda key, fetch, loaded, failed:
                        callbacks.append((loaded, failed)))
    try:
        window._carregar_historico_precos()
        loaded, failed = callbacks[-1]
        window.apply_session(conta_admin().session())
        loaded([event()])
        failed(RuntimeError('sensitive backend error from previous session'))
        page = window.historico_precos_page
        assert page.table.rowCount() == 0
        assert page.aviso_label.isHidden()
    finally:
        window.close()


def test_product_reload_preserves_user_filter_for_empty_intersection(page):
    page.carregar([event(user='Ana'), event(user='Bia')])
    page.usuario_combo.setCurrentIndex(page.usuario_combo.findData('Ana'))
    page.carregar([event(user='Bia')])  # existing product query returns only Bia's events
    assert page.usuario_combo.currentData() == 'Ana'
    assert page.table.rowCount() == 0
    page.limpar_filtros()
    assert page.table.rowCount() == 1
