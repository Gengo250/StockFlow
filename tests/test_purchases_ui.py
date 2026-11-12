from stockflow.presentation.demo_accounts import conta_admin
from stockflow.presentation.windows.main_window import MainWindow


def test_purchase_page_creates_draft_and_receives_all_items(qapp):
    window = MainWindow(conta_admin().session())
    try:
        page = window.compras_page
        assert window.show_page("compras")

        page.supplier_combo.setCurrentIndex(
            page.supplier_combo.findData("FOR-001")
        )
        page.product_combo.setCurrentIndex(
            page.product_combo.findData("PRD-009")
        )
        page.quantity_input.setValue(2)
        page.add_item_button.click()
        page.create_button.click()

        purchase = window.purchase_repository.list_all()[0]
        assert purchase.status.value == "RASCUNHO"
        assert window.products["PRD-009"].stock == "18"

        page.purchases_table.cellWidget(0, 4).click()

        purchase = window.purchase_repository.list_all()[0]
        assert purchase.status.value == "RECEBIDA"
        assert window.products["PRD-009"].stock == "20"
        movement = next(
            row for row in window.movement_repository.list_movements("PRD-009")
            if row[6] == f"Entrada de compra {purchase.purchase_id}"
        )
        assert movement[8] == "Distribuidora Central"
    finally:
        window.close()
