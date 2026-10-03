import os
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_PLATFORMTHEME'] = ''
os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'

from PySide6.QtWidgets import QApplication, QPushButton
from stockflow.presentation.demo_users import DEMO_USERS, USER_ROLES
from stockflow.presentation.widgets.user_form import UserForm
from stockflow.presentation.widgets.user_table import ACTIONS_COLUMN
from stockflow.presentation.windows.main_window import MainWindow


class UIRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_inventory_actions_forms_and_navigation(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        window.show_page('estoque')
        inventory = window.estoque_page
        for row, product in enumerate(inventory.produtos):
            edit = inventory.table.cellWidget(row, 6).findChildren(QPushButton)[0]
            edit.click()
            form = window.editar_produto_page
            self.assertIs(window.pages.currentWidget(), form)
            self.assertEqual(form.code_input.text(), product[0])
            self.assertEqual(form.name_input.text(), product[1])
            self.assertEqual(form.initial_stock_input.value(), int(product[3]))
            form.cancel_button.click()
            self.assertIs(window.pages.currentWidget(), inventory)
        form = window.novo_produto_page
        form.description_input.setPlainText('a' * 501)
        self.assertEqual(len(form.description_input.toPlainText()), 500)
        form.product_status_toggle.setChecked(False)
        self.assertEqual(form.status_label.text(), 'Inativo')
        form.product_status_toggle.setChecked(True)
        self.assertEqual(form.status_label.text(), 'Ativo')
        for key, page in (('estoque', inventory), ('produtos', window.products_page)):
            window.show_page(key)
            page.new_product_button.click()
            self.assertIs(window.pages.currentWidget(), form)
            form.back_button.click()
            self.assertIs(window.pages.currentWidget(), page)
            self.assertTrue(window.top_bar.isVisible())

    def test_catalog_reflow_and_filters(self):
        window = MainWindow()
        self.addCleanup(window.close)
        catalog = window.products_page
        catalog.setParent(None)
        self.addCleanup(catalog.close)
        catalog.show()
        for width, columns in ((1200, 3), (650, 2), (380, 1)):
            catalog.resize(width, 700)
            self.app.processEvents()
            self.assertEqual(catalog.grid.count(), 3)
            for index in range(3):
                self.assertEqual(catalog.grid.getItemPosition(index)[:2],
                                 (index // columns, index % columns))
            catalog.resize(width + 1, 700)
            self.app.processEvents()
            self.assertEqual(catalog.grid.count(), 3)
        catalog.search_input.setText('teclado')
        self.assertEqual(catalog.grid.count(), 1)
        self.assertFalse(catalog.cards['PRD-008'].isHidden())
        catalog.search_input.setText('missing')
        self.assertEqual(catalog.grid.count(), 0)
        self.assertTrue(catalog.empty_message.isVisible())
        catalog.search_input.clear()
        self.assertEqual(catalog.grid.count(), 3)

    def test_user_filters_and_edit_actions(self):
        # Linha de usuário:
        # (nome, login, departamento, perfil, status, último acesso, cor).
        # Este teste descrevia a base antiga de tres pessoas com perfil em
        # user[2] e acoes na coluna 2; seguia verde contra uma tela que nao
        # existe mais desde que a base passou a vir de demo_data.
        window = MainWindow()
        self.addCleanup(window.close)
        users = window.page_widgets['usuarios'].user_table
        users.edit_requested.disconnect()
        requested = []
        users.edit_requested.connect(requested.append)
        rows = range(len(DEMO_USERS))
        for row, user in enumerate(DEMO_USERS):
            users.table.cellWidget(row, ACTIONS_COLUMN).findChild(QPushButton).click()
            self.assertEqual(requested[-1], user)
            form = UserForm(user)
            self.assertEqual(form.name_input.text(), user[0])
            self.assertEqual(form.login_input.text(), user[1])
            self.assertEqual(form.role_input.currentText(), user[3])
            self.assertEqual(form.role_input.count(), len(USER_ROLES))
            form.close()
            # Varias pessoas dividem o mesmo perfil: o filtro mostra todas.
            users.filter_users(role=user[3])
            self.assertEqual(
                [i for i in rows if not users.table.isRowHidden(i)],
                [i for i, other in enumerate(DEMO_USERS) if other[3] == user[3]],
            )
            # O nome e unico, entao a busca isola a linha editada.
            users.filter_users(user[0])
            self.assertEqual([i for i in rows if not users.table.isRowHidden(i)], [row])
        users.filter_users('missing')
        self.assertTrue(all(users.table.isRowHidden(i) for i in rows))
        users.filter_users()
        self.assertTrue(all(not users.table.isRowHidden(i) for i in rows))


if __name__ == '__main__':
    unittest.main()
