import csv
from types import SimpleNamespace
from unittest.mock import Mock

from stockflow.presentation.pages.overview import ReportsPage


def test_report_filters_metrics_export_and_failure(qapp, tmp_path):
    products = Mock()
    products.list_all.return_value = [
        SimpleNamespace(code='P1', name='Monitor', category='Telas', stock='12', minimum_stock=5, active=True),
        SimpleNamespace(code='P2', name='=Formula', category='Telas', stock='3', minimum_stock=None, active=False),
    ]
    sales = Mock()
    sales.list_all.return_value = [
        dict(id='V1', cliente='Ana', produto='Monitor', total='1200.50', data='2026-10-14'),
        dict(id='V2', cliente='Bia', produto='Mouse', total='100', data='2026-10-13'),
    ]
    page = ReportsPage(products, sales)
    page.refresh()
    assert [label.text() for _, label in page.metrics] == ['2', '15', '1']
    page.status.setCurrentText('Inativos')
    assert len(page.rows) == 1
    path = tmp_path / 'report.csv'
    page.export_csv(path)
    with path.open(encoding='utf-8-sig') as output:
        exported = list(csv.reader(output, delimiter=';'))
    assert len(exported) == 2
    assert exported[1][1] == "'=Formula"
    page.search.setText('ausente')
    assert not page.rows and not page.export_button.isEnabled()
    page.search.clear()
    page.kind.setCurrentText('Vendas')
    assert [label.text() for _, label in page.metrics] == ['2', 'R$ 1.300,50', 'R$ 650,25']
    page.search.setText('ana')
    assert len(page.rows) == 1
    assert page.table.item(0, 3).text() == 'R$ 1.200,50'
    sales.list_all.side_effect = RuntimeError('Sem conexão')
    page.refresh()
    assert not page.rows and page.table.rowCount() == 0
    assert not page.export_button.isEnabled()
    assert 'Sem conexão' in page.error.text()
    assert all(label.text() == '—' for _, label in page.metrics)
    sales.list_all.side_effect = None
    page.refresh()
    assert len(page.rows) == 1 and page.export_button.isEnabled()
    page.close()
