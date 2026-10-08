"""Regressões da UI compatíveis com os contratos atuais da main."""
import os
import unittest
from dataclasses import replace

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_PLATFORMTHEME'] = ''
os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'

from PySide6.QtWidgets import QApplication, QSpinBox

from stockflow.presentation.demo_accounts import conta_admin
from stockflow.presentation.pages.novo_produto import NovoProdutoPage
from stockflow.presentation.windows.main_window import MainWindow


class RecoveredUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_stock_inputs_and_image_controls(self):
        page = NovoProdutoPage()
        self.addCleanup(page.close)
        for field in (page.initial_stock_input, page.minimum_stock_input):
            self.assertIsInstance(field, QSpinBox)
            field.setValue(123)
            self.assertEqual(field.value(), 123)
            field.setValue(9999999)
            self.assertEqual(field.value(), 999999)
        page.minimum_stock_input.setValue(-1)
        page.initial_stock_input.setValue(-1)
        self.assertEqual(page.minimum_stock_input.value(), -1)
        self.assertEqual(page.initial_stock_input.value(), 0)
        page.minimum_stock_input.setValue(0)
        self.assertEqual(page.minimum_stock_input.value(), 0)
        self.assertTrue(page.image_card.choose_button.isEnabled())
        page.image_card.set_image_data('invalid image')
        self.assertEqual(page.image_card.preview.text(), 'Sem imagem')
        page.image_card.remove_button.click()
        self.assertEqual(page.image_card.image_data, '')

    def test_movement_navigation_selection_and_permissions(self):
        window = MainWindow(conta_admin().session())
        self.addCleanup(window.close)
        window.sidebar.buttons['movimentacoes'].click()
        page = window.movimentacoes_page
        self.assertIs(window.pages.currentWidget(), page)
        self.assertIs(page.products, window.products)
        product = next(iter(window.products.values()))
        window.products[product.code] = replace(product, active=False)
        page.reload_products()
        self.assertEqual(page.produto_combo.findData(product.code), -1)
        page.apply_permission(False)
        self.assertFalse(page.registrar_button.isEnabled())
        self.assertFalse(page.registrar_confirmar_button.isEnabled())
        for key in ('fornecedores', 'clientes'):
            window.sidebar.buttons[key].click()
            self.assertIs(window.pages.currentWidget(), window.page_widgets[key])


if __name__ == '__main__':
    unittest.main()
