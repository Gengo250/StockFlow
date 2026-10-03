import os
import unittest
from dataclasses import replace

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_PLATFORMTHEME"] = ""
os.environ["QT_STYLE_OVERRIDE"] = "Fusion"

from PySide6.QtWidgets import QApplication

from stockflow.presentation.demo_accounts import conta_admin
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


if __name__ == "__main__":
    unittest.main()
