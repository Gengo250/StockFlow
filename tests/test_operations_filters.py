from unittest.mock import Mock

from stockflow.domain.entities.supplier import Supplier
from stockflow.presentation.pages.suppliers import SuppliersPage


def _linha_de(page, venda_id):
    """Posição da venda na tabela, sem presumir a ordem.

    Até a US17 este teste fixava `VND-1001` na linha 0, o que só passava
    porque o histórico saía na ordem de inserção. Com a consulta ordenada da
    mais recente para a mais antiga (SCRUM-218), `VND-1002` (28/09) vem
    antes de `VND-1001` (10/08) — e é essa a ordem correta.
    """
    for linha in range(page.table.rowCount()):
        if page.table.item(linha, 0).text() == venda_id:
            return linha
    raise AssertionError(f'{venda_id} não está na tabela')


def test_sales_history_is_ordered_newest_first(vendas_page):
    assert _linha_de(vendas_page, 'VND-1002') < _linha_de(vendas_page, 'VND-1001')
    vendas_page.close()


def test_sales_search_survives_history_reload(vendas_page):
    page = vendas_page
    procurada = _linha_de(page, 'VND-1001')
    outra = _linha_de(page, 'VND-1002')

    page.search_input.setText('VND-1001')
    assert not page.table.isRowHidden(procurada)
    assert page.table.isRowHidden(outra)

    page.reload_sales()
    assert not page.table.isRowHidden(procurada)
    assert page.table.isRowHidden(outra)

    page.search_input.setText('inexistente')
    assert '0 nesta página' in page.result_count.text()
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
