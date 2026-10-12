import os
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_PLATFORMTHEME'] = ''
os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'

from PySide6.QtWidgets import QApplication, QPushButton, QProgressBar
from stockflow.presentation.windows.main_window import MainWindow
from stockflow.presentation.pages.movimentacoes import ACTIONS_COLUMN


class MovementRegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.window.show_page('movimentacoes')
        self.page = self.window.movimentacoes_page
        self.page.produto_combo.setCurrentIndex(1)
        self.page.new_party_button.click()
        dialog = self.window.party_dialog
        dialog.name_input.setText('Fornecedor de teste')
        dialog.save_button.click()

    def test_register_entry_updates_history_inventory_catalog_and_dashboard(self):
        page = self.page
        page.quantidade_input.setValue(5)
        page.nota_input.setText('Reposição')
        page.registrar_confirmar_button.click()
        row = page.movimentacoes[0]
        self.assertEqual(row[3:7], ('Entrada', 5, 'Confirmada', 'Reposição'))
        self.assertEqual(row[8:11], ('Fornecedor de teste', 18, 23))
        self.assertEqual(self.window.products['PRD-009'].stock, '23')
        self.assertEqual(self.window.estoque_page.table.item(0, 3).text(), '23')
        self.assertEqual(self.window.products_page.cards['PRD-009'].findChild(QProgressBar).value(), 23)
        self.assertEqual(self.window.dashboard_page.metric_values[1].text(), '31')
        self.assertEqual(page.summary_values[0].text(), '5')
        self.assertEqual(page.quantidade_input.value(), 1)
        self.assertTrue(page.feedback_label.text())
        self.assertEqual(page.warning_label.text(), '')
        page.registrar_confirmar_button.click()
        self.assertEqual(len(page.movimentacoes), 1)
        self.assertIn('fornecedor', page.warning_label.text())

    def test_pending_confirm_once_cancel_and_reject_insufficient_stock(self):
        page = self.page
        page.quantidade_input.setValue(4)
        page.registrar_button.click()
        self.assertEqual(self.window.products['PRD-009'].stock, '18')
        pending_id = page.movimentacoes[0][0]
        buttons = page.table.cellWidget(0, ACTIONS_COLUMN).findChildren(QPushButton)
        buttons[1].click()
        self.assertEqual(self.window.products['PRD-009'].stock, '22')
        self.window._transition_movement(pending_id, True)
        self.assertEqual(self.window.products['PRD-009'].stock, '22')
        page.especie_combo.setCurrentIndex(1)
        page.quantidade_input.setValue(23)
        page.registrar_confirmar_button.click()
        self.assertIn('insuficiente', page.warning_label.text())
        self.assertEqual(len(page.movimentacoes), 1)
        self.assertEqual(page.quantidade_input.value(), 23)
        page.registrar_button.click()
        pending_id = page.movimentacoes[0][0]
        self.window._transition_movement(pending_id, True)
        self.assertEqual(page.movimentacoes[0][5], 'Pendente')
        self.assertEqual(self.window.products['PRD-009'].stock, '22')
        buttons = page.table.cellWidget(0, ACTIONS_COLUMN).findChildren(QPushButton)
        buttons[2].click()
        self.assertEqual(page.movimentacoes[0][5], 'Cancelada')
        page.quantidade_input.setValue(22)
        page.registrar_confirmar_button.click()
        self.assertEqual(self.window.products['PRD-009'].stock, '0')
        self.assertEqual(page.movimentacoes[0][9:11], (22, 0))
        page.apply_permission(False)
        count = len(page.movimentacoes)
        page._registrar(confirmar=True)
        self.assertEqual(len(page.movimentacoes), count)
        self.assertIn('permissão', page.warning_label.text())


if __name__ == '__main__':
    unittest.main()
