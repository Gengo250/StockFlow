from unittest.mock import Mock

from stockflow.domain.entities.supplier import Supplier
from stockflow.presentation.pages.suppliers import SuppliersPage


def test_sales_search_survives_history_reload(vendas_page):
    page = vendas_page
    page.search_input.setText('VND-1001')
    assert not page.table.isRowHidden(0)
    assert page.table.isRowHidden(1)
    page.reload_sales()
    assert not page.table.isRowHidden(0)
    assert page.table.isRowHidden(1)
    page.search_input.setText('inexistente')
    assert '0 de' in page.result_count.text()
    assert not page.empty_label.isHidden()
    page.close()


def test_supplier_filters_recover_from_load_error(qapp):
    service = Mock()
    service.list_suppliers.return_value = [
        Supplier(supplier_id='1', name='Fornecedor A', active=True),
        Supplier(supplier_id='2', name='Fornecedor B', active=False),
    ]
    page = SuppliersPage(service)
    page.status_filter.setCurrentText('Inativos')
    assert page.table.isRowHidden(0)
    assert not page.table.isRowHidden(1)
    page.search_input.setText('Fornecedor A')
    assert '0 de 2' in page.result_count.text()
    service.list_suppliers.side_effect = RuntimeError('Sem conexão')
    page.reload_table()
    page.search_input.clear()
    assert 'Sem conexão' in page.empty_label.text()
    assert page.table.rowCount() == 0
    service.list_suppliers.side_effect = None
    page.reload_table()
    assert page.table.isRowHidden(0)
    assert not page.table.isRowHidden(1)
    assert page.last_error is None
    page.close()
