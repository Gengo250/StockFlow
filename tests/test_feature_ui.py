from PySide6.QtGui import QImage

from stockflow.presentation.pages.movimentacoes import ACTIONS_COLUMN, PAGE_SIZE, MovimentacoesPage
from stockflow.presentation.widgets.product_form import ProductImageCard


def test_history_search_and_status_preserve_movement_actions(qapp):
    page = MovimentacoesPage()
    rows = (
        ('m1', 'P1', 'Monitor', 'Entrada', 2, 'Pendente', 'Compra', '2026-10-13', 'Fornecedor A', '—'),
        ('m2', 'P2', 'Teclado', 'Saída', 1, 'Confirmada', '', '2026-10-13', '', '—'),
    )
    page.set_movements(rows)
    page.search_input.setText('fornecedor a')
    assert page.table.rowCount() == 1
    assert 'Monitor' in page.table.item(0, 0).text()
    page.status_filter.setCurrentText('Confirmada')
    assert page.table.rowCount() == 0
    assert 'Nenhuma' in page.result_count.text()
    page.search_input.clear()
    received = []
    page.cancel_requested.connect(received.append)
    from PySide6.QtWidgets import QPushButton
    page.table.cellWidget(0, ACTIONS_COLUMN).findChildren(QPushButton)[1].click()
    assert received == ['m2']
    page.set_movements(rows)
    assert page.table.rowCount() == 1
    assert 'Teclado' in page.table.item(0, 0).text()
    page.close()


def test_movement_search_covers_all_pages_and_clear_resets_every_filter(qapp):
    page = MovimentacoesPage()
    try:
        rows = tuple(
            (f'm{i}', f'P{i}', f'Produto {i}', 'Entrada', 1, 'Pendente',
             'Compra', '2026-10-13', f'Fornecedor {i}', '—')
            for i in range(PAGE_SIZE + 1)
        )
        page.set_movements(rows)
        page.search_input.setText(f'Fornecedor {PAGE_SIZE}')
        assert page.table.rowCount() == 1
        assert f'P{PAGE_SIZE} —' in page.table.item(0, 0).text()
        assert not page.proximo_button.isEnabled()
        page.set_movements(rows)
        assert page.table.rowCount() == 1
        page.status_filter.setCurrentText('Confirmada')
        assert page.table.rowCount() == 0
        page.limpar_filtros()
        assert page.search_input.text() == ''
        assert page.status_filter.currentIndex() == 0
        assert page.table.rowCount() == PAGE_SIZE
        assert page.proximo_button.isEnabled()
    finally:
        page.close()


def test_product_image_can_be_selected_and_removed(qapp, tmp_path):
    path = tmp_path / 'product.png'
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(0x336699)
    assert image.save(str(path))
    card = ProductImageCard()
    assert not card.remove_button.isEnabled()
    card.load_image(str(path))
    assert card.image_data
    assert card.choose_button.text() == 'Trocar imagem'
    assert card.remove_button.isEnabled()
    card.remove_button.click()
    assert card.image_data == ''
    assert not card.remove_button.isEnabled()
    assert card.preview.pixmap().isNull()
    card.close()


def test_product_edit_preserves_fields_not_exposed_in_form(qapp):
    from dataclasses import replace
    from stockflow.presentation.demo_products import DEMO_PRODUCTS
    from stockflow.presentation.pages.novo_produto import NovoProdutoPage

    page = NovoProdutoPage(edit_mode=True)
    try:
        product = replace(next(iter(DEMO_PRODUCTS.values())), ncm='12345678',
                          ean='1234567890123', maximum_stock=100)
        page.load_product(product)
        page.name_input.setText('Nome atualizado')
        data = page.collect_input()
        assert (data.ncm, data.ean, data.maximum_stock) == ('12345678', '1234567890123', 100)
        page.clear_form()
        data = page.collect_input()
        assert (data.ncm, data.ean, data.maximum_stock) == ('', '', None)
    finally:
        page.close()


def test_empty_movement_search_is_not_reported_as_empty_history(qapp):
    page = MovimentacoesPage()
    try:
        page.set_movements((('m1', 'P1', 'Monitor', 'Entrada', 2, 'Pendente',
                             'Compra', '2026-10-13', 'Fornecedor A', '—'),))
        page.search_input.setText('inexistente')
        assert 'filtros' in page.list_state_label.text()
        assert 'filtro ativo' in page.subtitle.text()
        page.search_input.clear()
        page.status_filter.setCurrentText('Confirmada')
        assert 'filtros' in page.list_state_label.text()
    finally:
        page.close()
