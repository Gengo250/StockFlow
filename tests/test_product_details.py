import os
import unittest
from dataclasses import replace

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_PLATFORMTHEME"] = ""
os.environ["QT_STYLE_OVERRIDE"] = "Fusion"

from PySide6.QtWidgets import QApplication

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_admin, conta_por_papel
from stockflow.presentation.windows.main_window import MainWindow


class ProductDetailsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_catalog_details_return_and_failure(self):
        window = MainWindow(conta_admin().session())
        self.addCleanup(window.close)
        window.show()
        window.sidebar.buttons["produtos"].click()
        catalog = window.products_page
        details = window.product_details_page
        catalog.search_input.setText("teclado")
        self.assertTrue(catalog.cards["PRD-009"].isHidden())
        self.assertFalse(catalog.cards["PRD-008"].isHidden())
        catalog.cards["PRD-008"].click()
        self.assertIs(window.pages.currentWidget(), details)
        product = window.products["PRD-008"]
        for key in ("code", "name", "category", "unit", "sale_price", "cost"):
            self.assertEqual(details.values[key].text(), getattr(product, key))
        self.assertEqual(details.values["active"].text(), "Ativo")
        self.assertTrue(window.top_bar.isVisible())
        details.back_button.click()
        self.assertIs(window.pages.currentWidget(), catalog)
        self.assertEqual(catalog.search_input.text(), "teclado")

        window.products[product.code] = replace(product, active=False)
        catalog.cards["PRD-008"].click()
        self.assertEqual(details.values["active"].text(), "Inativo")
        del window.products[product.code]
        details.back_button.click()
        catalog.cards["PRD-008"].click()
        self.assertTrue(details.error_message.isVisible())
        self.assertFalse(details.scroll.isVisible())
        self.assertTrue(all(not label.text() for label in details.values.values()))
        details.back_button.click()
        catalog.search_input.clear()
        catalog.cards["PRD-009"].click()
        self.assertFalse(details.error_message.isVisible())
        self.assertEqual(details.values["code"].text(), "PRD-009")
        details.back_button.click()
        catalog.new_product_button.click()
        self.assertIs(window.pages.currentWidget(), window.novo_produto_page)
        window.novo_produto_page.cancel_button.click()
        self.assertIs(window.pages.currentWidget(), catalog)
        catalog.search_input.setText("inexistente")
        self.assertTrue(catalog.empty_message.isVisible())

    def test_supplier_name_is_shown_only_to_roles_that_can_read_suppliers(self):
        for role in (UserRole.ADMIN, UserRole.STOCK):
            with self.subTest(role=role):
                window = MainWindow(conta_por_papel(role).session())
                self.addCleanup(window.close)
                window.show()
                product = window.products["PRD-009"]
                window.products[product.code] = replace(
                    product, supplier_id="FOR-001"
                )
                window.products_page.cards[product.code].click()

                details = window.product_details_page
                self.assertTrue(details.supplier_label.isVisible())
                self.assertEqual(
                    details.values["supplier"].text(), "Distribuidora Central"
                )
                if role is UserRole.ADMIN:
                    window.apply_session(
                        conta_por_papel(UserRole.SELLER).session()
                    )
                    self.assertFalse(details.supplier_label.isVisible())
                    self.assertEqual(details.values["supplier"].text(), "")

        seller = MainWindow(conta_por_papel(UserRole.SELLER).session())
        self.addCleanup(seller.close)
        seller.show()
        product = seller.products["PRD-009"]
        seller.products[product.code] = replace(product, supplier_id="FOR-001")
        seller.products_page.cards[product.code].click()

        self.assertFalse(seller.product_details_page.supplier_label.isVisible())
        self.assertEqual(seller.product_details_page.values["supplier"].text(), "")

    def test_unassigned_product_has_optional_supplier_label(self):
        window = MainWindow(conta_admin().session())
        self.addCleanup(window.close)
        window.show()
        window.products_page.cards["PRD-009"].click()

        details = window.product_details_page
        self.assertTrue(details.supplier_label.isVisible())
        self.assertEqual(details.values["supplier"].text(), "Não informado")


if __name__ == "__main__":
    unittest.main()
