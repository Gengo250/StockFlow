import os
import unittest
from datetime import datetime, timezone

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_PLATFORMTHEME'] = ''
os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QAbstractItemView, QPushButton
from stockflow.presentation.pages.movimentacoes import MovimentacoesPage, ACTIONS_COLUMN
from stockflow.presentation.dialogs.movement_details import movement_datetime


class MovementHistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.page = MovimentacoesPage()
        self.addCleanup(self.page.close)
        self.rows = [
            ('old', 'P1', 'Café', 'Entrada', 10, 'Confirmada', '', '30/09/2026 10:00', 'Fornecedor', 0, 10, 'Compra', 'Ana', None),
            ('sale', 'P1', 'Café', 'Saída', 3, 'Confirmada', 'Venda no balcão', '2026-10-08T15:30:00Z', 'Cliente', 10, 7, 'Venda', 'Bruno', 'V-42'),
            ('pending', 'P2', 'Leite', 'Entrada', 4, 'Pendente', '', '2026-10-08T18:00:00Z', None, None, None, 'Manual', 'Ana', None),
        ]
        self.page.set_movements(self.rows)

    def visible_ids(self):
        return [m[0] for row, m in enumerate(self.page.movimentacoes) if not self.page.table.isRowHidden(row)]

    def test_order_and_combined_inclusive_filters(self):
        self.assertEqual(self.visible_ids(), ['pending', 'sale', 'old'])
        self.page.product_filter.setText('p1')
        self.page.kind_filter.setCurrentText('Saída')
        self.page.actor_filter.setText('brUNO')
        self.page.date_from.setDate(QDate(2026, 10, 8))
        self.page.date_to.setDate(QDate(2026, 10, 8))
        self.page.period_filter.setChecked(True)
        self.assertEqual(self.visible_ids(), ['sale'])
        self.page.set_movements(self.rows)
        self.assertEqual(self.visible_ids(), ['sale'])
        self.page.date_from.setDate(QDate(2026, 10, 9))
        self.assertEqual(self.visible_ids(), [])
        self.assertIn('data inicial', self.page.filter_state.text())
        self.page._clear_filters()
        self.assertEqual(len(self.visible_ids()), 3)
        self.page.product_filter.setText('inexistente')
        self.assertEqual(self.visible_ids(), [])

    def test_read_only_details_and_missing_legacy_data(self):
        self.page._show_details(self.page.movimentacoes[1])
        dialog = self.page.details_dialog
        self.assertEqual(dialog.values['Saldo anterior'].text(), '10')
        self.assertEqual(dialog.values['Saldo resultante'].text(), '7')
        self.assertEqual(dialog.values['Venda vinculada'].text(), 'V-42')
        self.assertEqual(dialog.values['Origem'].text(), 'Venda')
        self.assertEqual(dialog.values['Responsável'].text(), 'Bruno')
        dialog.close()
        self.page.set_movements([self.rows[0][:8]])
        self.page._show_details(self.page.movimentacoes[0])
        dialog = self.page.details_dialog
        self.assertEqual(dialog.values['Saldo anterior'].text(), 'Não informado')
        dialog.close()
        self.assertEqual(self.page.table.editTriggers(), QAbstractItemView.NoEditTriggers)

    def test_confirmed_mutations_blocked_even_via_direct_request(self):
        received = []
        self.page.cancel_requested.connect(received.append)
        self.page.confirm_requested.connect(received.append)
        for signal in (self.page.cancel_requested, self.page.confirm_requested):
            self.page._request_pending('sale', signal)
            self.page._request_pending('missing', signal)
        self.assertEqual(received, [])
        buttons = self.page.table.cellWidget(1, ACTIONS_COLUMN).findChildren(QPushButton)
        self.assertTrue(buttons[0].isEnabled())
        self.assertTrue(all(not button.isEnabled() for button in buttons[1:]))
        self.page._request_pending('pending', self.page.cancel_requested)
        self.assertEqual(received, ['pending'])
        self.page.apply_permission(False)
        self.page._request_pending('pending', self.page.cancel_requested)
        self.assertEqual(received, ['pending'])
        self.page.apply_permission(True)
        changed = list(self.rows[2])
        changed[5] = 'Confirmada'
        self.page.set_movements([changed])
        self.page._request_pending('pending', self.page.cancel_requested)
        self.assertEqual(received, ['pending'])
        changed[5] = 'Cancelada'
        self.page.set_movements([changed])
        self.page._request_pending('pending', self.page.confirm_requested)
        self.assertEqual(received, ['pending'])

    def test_dates_unknown_values_and_load_errors(self):
        self.assertEqual(movement_datetime('2026-10-08T12:30:00-03:00'), datetime(2026, 10, 8, 15, 30))
        self.assertEqual(movement_datetime(datetime(2026, 10, 8, tzinfo=timezone.utc)), datetime(2026, 10, 8))
        unknown = ('unknown', 'P1', 'Café', 'Entrada', 2, 'Confirmada', '', 'Hoje')
        self.page.set_movements([unknown, *self.rows])
        self.assertEqual(self.visible_ids()[-1], 'unknown')
        self.page.period_filter.setChecked(True)
        self.assertNotIn('unknown', self.visible_ids())
        self.page.show_load_error('Sem conexão')
        self.page.product_filter.setText('Café')
        self.assertTrue(self.page.table.isHidden())
        self.page.set_movements([])
        self.assertFalse(self.page.table.isHidden())
        self.assertTrue(self.page.load_error_label.isHidden())


if __name__ == '__main__':
    unittest.main()
