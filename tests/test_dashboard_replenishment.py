from dataclasses import replace
from unittest.mock import Mock

from stockflow.domain.replenishment import suggest_replenishment
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.presentation.pages.dashboard import DashboardPage


def product(code, stock, minimum, active=True):
    return replace(next(iter(DEMO_PRODUCTS.values())), code=code, stock=str(stock), minimum_stock=minimum, active=active)


def test_replenishment_priorities_thresholds_and_exclusions():
    suggestions = suggest_replenishment([
        product('no-minimum', 0, None), product('inactive', 0, 10, False),
        product('healthy', 20, 10), product('attention', 11, 10),
        product('at-minimum', 10, 10), product('zero-minimum', 0, 0),
        product('critical', 0, 6),
    ])
    assert [item.code for item in suggestions] == ['critical', 'zero-minimum', 'at-minimum']
    assert [(item.target, item.quantity) for item in suggestions] == [(8, 8), (1, 1), (12, 2)]


def test_dashboard_data_filters_failure_and_recovery(qapp):
    products, sales, clients = Mock(), Mock(), Mock()
    products.list_all.return_value = [product('P1', 0, 5), product('P2', 10, 10)]
    sales.list_all.return_value = [{'total': '1200.50'}]
    clients.list_all.return_value = []
    page = DashboardPage(products, sales, clients)
    page.refresh()
    assert [value.text() for value in page.metric_values] == ['2', '2', 'R$ 1.200,50', '0']
    page.search_input.setText('P2')
    assert page.table.isRowHidden(0) and not page.table.isRowHidden(1)
    products.list_all.side_effect = RuntimeError('Sem conexão')
    page.refresh()
    assert page.table.rowCount() == 0
    assert all(value.text() == '—' for value in page.metric_values)
    assert 'Sem conexão' in page.summary.text()
    page.search_input.clear()
    assert 'Não foi possível consultar' in page.empty_label.text()
    products.list_all.side_effect = None
    products.list_all.return_value = []
    page.refresh()
    page.search_input.clear()
    assert 'Nenhum produto precisa' in page.empty_label.text()
    assert page.metric_values[0].text() == '0'
    assert page.refresh_button.isEnabled()
    page.close()
