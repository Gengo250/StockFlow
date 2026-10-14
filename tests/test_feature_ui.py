from PySide6.QtGui import QImage

from stockflow.presentation.pages.movimentacoes import MovimentacoesPage
from stockflow.presentation.widgets.product_form import ProductImageCard


def test_history_search_and_status_preserve_movement_actions(qapp):
    page = MovimentacoesPage()
    rows = (
        ('m1', 'P1', 'Monitor', 'Entrada', 2, 'Pendente', 'Compra', '2026-10-13', 'Fornecedor A'),
        ('m2', 'P2', 'Teclado', 'Saída', 1, 'Confirmada', '', '2026-10-13', ''),
    )
    page.set_movements(rows)
    page.search_input.setText('fornecedor a')
    assert not page.table.isRowHidden(0)
    assert page.table.isRowHidden(1)
    page.status_filter.setCurrentText('Confirmada')
    assert page.table.isRowHidden(0)
    assert 'Nenhuma' in page.result_count.text()
    page.search_input.clear()
    received = []
    page.cancel_requested.connect(received.append)
    from PySide6.QtWidgets import QPushButton
    page.table.cellWidget(1, 7).findChildren(QPushButton)[1].click()
    assert received == ['m2']
    page.set_movements(rows)
    assert page.table.isRowHidden(0)
    assert not page.table.isRowHidden(1)
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
