import os
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_PLATFORMTHEME'] = ''
os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'

from PySide6.QtWidgets import QApplication
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.presentation.windows.main_window import MainWindow


class PartyRegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.window.show()
        self.window.show_page('movimentacoes')
        self.page = self.window.movimentacoes_page

    def test_create_validate_cancel_and_reuse_supplier(self):
        page = self.page
        page.quantidade_input.setValue(7)
        page.nota_input.setText('Compra de teste')
        page.new_party_button.click()
        dialog = self.window.party_dialog
        self.assertTrue(dialog.isVisible())
        dialog.name_input.setText('   ')
        dialog.save_button.click()
        self.assertTrue(dialog.isVisible())
        self.assertTrue(dialog.error_label.text())
        self.assertEqual(page.fornecedor_combo.count(), 1)
        dialog.name_input.setText('  Fornecedor  Teste  ')
        dialog.save_button.click()
        self.assertEqual(page.fornecedor_combo.currentText(), 'Fornecedor Teste')
        supplier_id = page.fornecedor_combo.currentData()
        self.assertTrue(supplier_id)
        self.assertEqual(page.quantidade_input.value(), 7)
        self.assertEqual(page.nota_input.text(), 'Compra de teste')
        self.window.show_page('dashboard')
        self.window.show_page('movimentacoes')
        self.assertEqual(page.fornecedor_combo.currentData(), supplier_id)
        page.new_party_button.click()
        self.window.party_dialog.name_input.setText('fornecedor teste')
        self.window.party_dialog.save_button.click()
        self.assertEqual(page.fornecedor_combo.count(), 2)
        self.assertEqual(page.fornecedor_combo.currentData(), supplier_id)
        page.new_party_button.click()
        self.window.party_dialog.name_input.setText('Descartado')
        self.window.party_dialog.cancel_button.click()
        self.assertEqual(page.fornecedor_combo.count(), 2)
        requests = []
        page.register_requested.connect(requests.append)
        page.produto_combo.setCurrentIndex(1)
        page.registrar_confirmar_button.click()
        self.assertEqual(requests[0].supplier_id, supplier_id)

    def test_client_and_permission_revoked_while_dialog_open(self):
        page = self.page
        page.especie_combo.setCurrentIndex(page.especie_combo.findData(MovementKind.SAIDA))
        page.new_party_button.click()
        self.assertIn('cliente', self.window.party_dialog.windowTitle())
        self.window.party_dialog.name_input.setText('Cliente Teste')
        self.window.party_dialog.save_button.click()
        self.assertEqual(page.cliente_combo.currentText(), 'Cliente Teste')
        self.assertEqual(page.fornecedor_combo.count(), 1)
        page.new_party_button.click()
        dialog = self.window.party_dialog
        page.set_party_permissions(True, False)
        dialog.name_input.setText('Sem permissão')
        dialog.save_button.click()
        self.assertEqual(page.cliente_combo.count(), 2)
        self.assertFalse(page.new_party_button.isEnabled())
        self.assertIn('permissão', page.warning_label.text())


if __name__ == '__main__':
    unittest.main()
