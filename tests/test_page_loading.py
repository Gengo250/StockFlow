"""Regressões de navegação com consultas lentas e respostas atrasadas."""
import threading
import time

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from stockflow.presentation.workers import PageLoader, executar_em_segundo_plano


def until(qapp, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        QTest.qWait(1)
    assert predicate()


def test_read_does_not_block_ui_and_callbacks_return_to_ui(qapp):
    owner = QWidget()
    loader = PageLoader(owner, executar_em_segundo_plano)
    gate = threading.Event()
    entered = threading.Event()
    results, beats, threads = [], [], []
    ui_thread = threading.get_ident()
    timer = QTimer()
    timer.timeout.connect(lambda: beats.append(1))
    timer.start(1)

    def fetch():
        threads.append(threading.get_ident())
        entered.set()
        assert gate.wait(5)
        return 42

    try:
        loader.load(fetch, lambda result: results.append((result, threading.get_ident())),
                    lambda error: pytest.fail(str(error)))
        assert entered.wait(2)
        until(qapp, lambda: len(beats) >= 3)
        assert not results
        gate.set()
        until(qapp, lambda: bool(results))
        assert threads[0] != ui_thread
        assert results == [(42, ui_thread)]
    finally:
        gate.set()
        timer.stop()
        owner.close()


def test_only_latest_queued_read_is_applied_and_close_ignores_result(qapp):
    owner = QWidget()
    jobs, results = [], []
    loader = PageLoader(owner, lambda *job: jobs.append(job))
    loader.load(lambda: 'old', results.append, results.append)
    loader.load(lambda: 'discarded', results.append, results.append)
    loader.load(lambda: 'latest', results.append, results.append)
    assert len(jobs) == 1
    jobs[0][1](jobs[0][0]())
    assert results == []
    assert len(jobs) == 2
    jobs[1][1](jobs[1][0]())
    assert results == ['latest']
    loader.load(lambda: 'after close', results.append, results.append)
    loader.close()
    jobs[2][1](jobs[2][0]())
    assert results == ['latest']


def test_remote_window_build_and_navigation_do_not_read_synchronously(qapp, monkeypatch):
    from stockflow.presentation.windows import main_window as module
    from stockflow.presentation.demo_accounts import conta_admin
    monkeypatch.setenv('STOCKFLOW_BACKEND', 'demo')
    monkeypatch.setattr(module, 'using_supabase', lambda: True)
    jobs = []
    monkeypatch.setattr(module, 'executar_em_segundo_plano', lambda *job: jobs.append(job))
    window = module.MainWindow(conta_admin().session())
    assert window.clientes_page.table.rowCount() == 0
    assert window.suppliers_page.table.rowCount() == 0
    assert window.vendas_page.historico_vendas == []
    assert window.historico_precos_page.table.rowCount() == 0
    assert jobs  # Only the visible dashboard was scheduled.
    try:
        synchronous_reads = []

        def forbidden(*args, **kwargs):
            synchronous_reads.append(1)
            raise AssertionError('I/O executed in the navigation handler')
        monkeypatch.setattr(window.product_repository, 'list_all', forbidden)
        monkeypatch.setattr(window.sale_repository, 'list_all', forbidden)
        monkeypatch.setattr(window.client_repository, 'list_all', forbidden)
        monkeypatch.setattr(window.supplier_service, 'list_suppliers', forbidden)
        monkeypatch.setattr(window.movement_service, 'list_movements', forbidden)
        monkeypatch.setattr(window.price_history_service, 'list_changes', forbidden)
        monkeypatch.setattr(module, 'build_user_directory', forbidden)
        for key in ('dashboard', 'relatorios', 'clientes', 'vendas', 'fornecedores',
                    'movimentacoes', 'historico_precos', 'usuarios'):
            assert window.show_page(key)
            assert window.pages.currentWidget() is window.page_widgets[key]
        assert synchronous_reads == []
        assert len(jobs) >= 8
        window.close()
        # In-flight callbacks cannot mutate widgets or show dialogs after logout.
        for _, loaded, failed in jobs:
            failed(RuntimeError('late network error'))
    finally:
        window.close()


def test_report_type_change_during_load_discards_old_shape(qapp):
    from stockflow.presentation.pages.reports import ReportsPage
    from stockflow.infrastructure.repositories.demo_product_repository import DemoProductRepository
    from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
    from stockflow.presentation.demo_products import DEMO_PRODUCTS
    page = ReportsPage(DemoProductRepository(dict(DEMO_PRODUCTS)), DemoSaleRepository(dict(DEMO_PRODUCTS)))
    jobs = []
    page.loader.execute = lambda *job: jobs.append(job)
    page.refresh()
    page.kind.setCurrentIndex(1)
    jobs[0][1](jobs[0][0]())
    assert page.rows == []
    jobs[1][1](jobs[1][0]())
    assert page.headers[0] == 'Venda'
    assert all(len(row) == 5 for row in page.rows)
    assert page.refresh_button.isEnabled()
    page.close()


def test_clients_share_one_read_with_sales(qapp):
    from stockflow.presentation.pages.clientes import ClientesPage
    from stockflow.presentation.pages.vendas import VendasPage
    from stockflow.presentation.demo_accounts import conta_admin
    from stockflow.infrastructure.repositories.demo_client_repository import DemoClientRepository
    repository = DemoClientRepository()
    calls = []
    original = repository.list_all
    repository.list_all = lambda: (calls.append(1), original())[1]
    sales = VendasPage(autoload=False)
    page = ClientesPage(sales_page=sales, repository=repository,
                        session=conta_admin().session(), autoload=False)
    page.reload_table()
    assert len(calls) == 1
    assert len(sales.clientes) == page.table.rowCount()
    page.close()
    sales.close()


def test_catalog_reuses_unchanged_cards(qapp):
    from dataclasses import replace
    from stockflow.presentation.demo_products import DEMO_PRODUCTS
    from stockflow.presentation.pages.products import ProductsPage
    products = dict(DEMO_PRODUCTS)
    page = ProductsPage(products)
    original = dict(page.cards)
    page.reload_products()
    assert all(page.cards[code] is card for code, card in original.items())
    code = next(iter(products))
    products[code] = replace(products[code], name='Produto atualizado')
    page.reload_products()
    assert page.cards[code] is not original[code]
    assert all(page.cards[key] is card for key, card in original.items() if key != code)
    page.close()


def test_remote_login_prevents_duplicate_submit_and_allows_retry(qapp, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    from stockflow.presentation.windows import login_window as module
    jobs = []
    monkeypatch.setattr(module, 'using_supabase', lambda: True)
    monkeypatch.setattr(module, 'executar_em_segundo_plano', lambda *job: jobs.append(job))
    login = module.LoginWindow(QSettings(str(tmp_path / 'login.ini'), QSettings.IniFormat))
    login.email_input.setText('person@example.test')
    login.password_input.setText('test-password')
    login._submit()
    login._submit()
    assert len(jobs) == 1
    assert not login.submit_button.isEnabled()
    jobs[0][2](RuntimeError('Servidor indisponível'))
    assert login.submit_button.isEnabled()
    assert login.error.text() == 'Servidor indisponível'
    login._submit()
    assert len(jobs) == 2
    jobs[1][1](None)
    assert login.submit_button.isEnabled()
    assert not login.password_input.text()
    login.close()
