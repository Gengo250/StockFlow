import os
import unittest
from dataclasses import replace

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_PLATFORMTHEME'] = ''
os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'

from PySide6.QtWidgets import QApplication
from stockflow.presentation.windows.main_window import MainWindow


class DashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_summary_navigation_and_refresh(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        page = window.dashboard_page
        self.assertEqual([v.text() for v in page.metric_values], ['3', '26', '2', '2'])
        page.alert_buttons[0].click()
        self.assertIs(window.pages.currentWidget(), window.product_details_page)
        for button, key in ((page.inventory_button, 'estoque'),
                            (page.catalog_button, 'produtos'),
                            (page.movements_button, 'movimentacoes')):
            window.show_page('dashboard')
            button.click()
            self.assertIs(window.pages.currentWidget(), window.page_widgets[key])
        window.show_page('dashboard')
        page.new_product_button.click()
        window.novo_produto_page.back_button.click()
        self.assertIs(window.pages.currentWidget(), page)
        window.show_page('produtos')
        window.products['PRD-007'] = replace(window.products['PRD-007'], stock='12', stock_status='Normal')
        window.show_page('dashboard')
        self.assertEqual([v.text() for v in page.metric_values], ['3', '36', '1', '2'])
        window.products.clear()
        page.refresh()
        self.assertEqual([v.text() for v in page.metric_values], ['0', '0', '0', '0'])
        self.assertEqual(page.alert_buttons, [])

    def test_responsive_layout(self):
        window = MainWindow()
        self.addCleanup(window.close)
        page = window.dashboard_page
        page.setParent(None)
        self.addCleanup(page.close)
        page.show()
        for width, columns in ((1200, 4), (760, 2), (430, 1)):
            page.resize(width, 800)
            self.app.processEvents()
            self.assertEqual(page._columns, columns)
            self.assertEqual(page.scroll.horizontalScrollBar().maximum(), 0)
            for index in range(4):
                self.assertEqual(page.metrics_grid.getItemPosition(index)[:2],
                                 (index // columns, index % columns))


if __name__ == '__main__':
    unittest.main()
