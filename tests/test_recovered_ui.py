import os
import unittest
from dataclasses import replace

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_PLATFORMTHEME'] = ''
os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout, QLineEdit

from stockflow.presentation.pages.novo_produto import NovoProdutoPage
from stockflow.presentation.windows.main_window import MainWindow


class RecoveredUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_stock_inputs_and_image_placeholder(self):
        page = NovoProdutoPage()
        self.addCleanup(page.close)
        for field in (page.initial_stock_input, page.minimum_stock_input):
            self.assertIsInstance(field, QLineEdit)
            field.clear()
            QTest.keyClicks(field, 'abc-12.3,+')
            self.assertEqual(field.text(), '123')
            self.app.clipboard().setText('invalid')
            field.paste()
            self.assertEqual(field.text(), '123')
            event = QWheelEvent(
                QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, 120),
                Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
            )
            QApplication.sendEvent(field, event)
            self.assertEqual(field.text(), '123')
            field.selectAll()
            QTest.keyClicks(field, '9999999')
            self.assertEqual(field.value(), 999999)
        page.minimum_stock_input.clear()
        page.initial_stock_input.clear()
        self.assertEqual(page.minimum_stock_input.value(), -1)
        self.assertEqual(page.initial_stock_input.value(), 0)
        QTest.keyClicks(page.minimum_stock_input, '0')
        self.assertEqual(page.minimum_stock_input.value(), 0)
        self.assertEqual(page.image_card.choose_button.text(), 'Em desenvolvimento')
        self.assertFalse(page.image_card.choose_button.isEnabled())
        self.assertTrue(page.image_card.remove_button.isHidden())

    def test_movement_navigation_totals_selection_and_layout(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        window.sidebar.buttons['movimentacoes'].click()
        page = window.movimentacoes_page
        self.assertIs(window.pages.currentWidget(), page)
        self.assertIs(page.products, window.products)
        page.set_movements([
            ('1', 'A', 'Produto', 'Entrada', 12, 'Confirmada', '', 'Hoje'),
            ('2', 'A', 'Produto', 'Saída', 4, 'Confirmada', '', 'Hoje'),
            ('3', 'A', 'Produto', 'Entrada', 20, 'Pendente', '', 'Hoje'),
            ('4', 'A', 'Produto', 'Saída', 2, 'Cancelada', '', 'Hoje'),
        ])
        self.assertEqual([label.text() for label in page.summary_values], ['12', '4', '4'])
        page.kind_buttons[1].click()
        self.assertEqual(page.party_label.text(), 'Cliente')
        self.assertEqual(page.registrar_confirmar_button.text(), 'Registrar saída')
        received = []
        page.register_requested.connect(received.append)
        page.produto_combo.setCurrentIndex(1)
        page.registrar_button.click()
        self.assertEqual(len(received), 1)
        page.produto_combo.setEditText('Produto inexistente')
        page.registrar_button.click()
        self.assertEqual(len(received), 1)
        product = next(iter(window.products.values()))
        window.products[product.code] = replace(product, active=False)
        page.reload_products()
        self.assertEqual(page.produto_combo.findData(product.code), -1)
        page.apply_permission(False)
        self.assertTrue(all(not button.isEnabled() for button in page.kind_buttons))
        for width, direction in ((1600, QBoxLayout.LeftToRight), (1000, QBoxLayout.TopToBottom)):
            window.resize(width, 900)
            self.app.processEvents()
            self.assertEqual(page.body_layout.direction(), direction)


if __name__ == '__main__':
    unittest.main()
