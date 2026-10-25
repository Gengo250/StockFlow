"""Capture the demo interface without touching a remote backend.

Run from the repository: uv run python docs/ui/2026-10-23/capture.py OUTPUT
"""
import argparse
import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_PLATFORMTHEME"] = ""
os.environ["QT_STYLE_OVERRIDE"] = "Fusion"
os.environ["STOCKFLOW_BACKEND"] = "demo"

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea
from stockflow.presentation.demo_accounts import conta_admin
from stockflow.presentation.demo_users import DEMO_USERS
from stockflow.presentation.windows.main_window import MainWindow
from stockflow.presentation.windows.login_window import LoginWindow
from stockflow.presentation.pages.movement_details import MovementDetailsPage
from stockflow.presentation.widgets.user_form import UserForm
from stockflow.presentation.widgets.category_form import CategoryDialog
from stockflow.presentation.widgets.password_recovery import PasswordRecoveryDialog
from stockflow.presentation.styles.users import USERS_QSS


def capture(output):
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setCursorFlashTime(0)
    manifest = []

    def shot(widget, name):
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        path = output / (name + ".png")
        if not widget.grab().save(str(path)):
            raise RuntimeError(path)
        manifest.append(path.name)

    for width, height in ((1440, 900), (1024, 768)):
        prefix = str(width)
        window = MainWindow(conta_admin().session())
        window.resize(width, height)
        window.show()
        for key in window.page_widgets:
            window.show_page(key)
            shot(window, f"{prefix}-{key}")
        window.show_page("estoque")
        window.estoque_page.search_input.setText("sem-resultado-de-captura")
        shot(window, f"{prefix}-stock-empty")
        window.estoque_page.begin_loading()
        shot(window, f"{prefix}-stock-loading")
        window.estoque_page.show_load_error(RuntimeError("Fonte indisponível para captura de estado."))
        shot(window, f"{prefix}-stock-error")
        window._show_new_product("produtos")
        shot(window, f"{prefix}-new-product")
        scroll = window.novo_produto_page.findChild(QScrollArea)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        shot(window, f"{prefix}-new-product-bottom")
        # Use the catalog object to bypass the pre-existing eight-field tuple bug.
        window.editar_produto_page.load_product(window.products["PRD-009"])
        window.pages.setCurrentWidget(window.editar_produto_page)
        shot(window, f"{prefix}-edit-product")
        window._show_product_details("PRD-009")
        shot(window, f"{prefix}-product-details")
        window._show_product_details("missing")
        shot(window, f"{prefix}-product-error")
        window.show_page("vendas")
        sale = window.vendas_page
        sale.cliente_combo.setCurrentIndex(1)
        sale.produto_combo.setCurrentIndex(1)
        sale.qtd_input.setText("1")
        sale.add_button.click()
        shot(window, f"{prefix}-sale-cart")
        outer_scroll = sale.parentWidget().parentWidget()
        outer_scroll.verticalScrollBar().setValue(outer_scroll.verticalScrollBar().maximum())
        shot(window, f"{prefix}-sale-history")
        window.show_page("movimentacoes")
        page = window.movimentacoes_page
        outer_scroll = page.parentWidget().parentWidget()
        outer_scroll.verticalScrollBar().setValue(outer_scroll.verticalScrollBar().maximum())
        shot(window, f"{prefix}-movement-history")
        for user, label in ((None, "new-user"), (DEMO_USERS[0], "edit-user")):
            form = UserForm(user, window, pode_gerenciar=True)
            form.setStyleSheet(USERS_QSS)
            form.show()
            shot(form, f"{prefix}-{label}")
            form.close()
        category = CategoryDialog(["Eletrônicos", "Periféricos"], parent=window)
        category.show()
        shot(category, f"{prefix}-categories")
        category.close()
        for area, objects in (("clientes", window.clientes_page._clients),
                              ("fornecedores", window.suppliers_page._suppliers)):
            page = window.page_widgets[area]
            for record, mode in ((None, "new"), (objects[0], "edit")):
                original_exec = QDialog.exec
                def capture_dialog(dialog, name=f"{prefix}-{mode}-{area}"):
                    dialog.show()
                    shot(dialog, name)
                    dialog.reject()
                    return QDialog.Rejected
                QDialog.exec = capture_dialog
                try:
                    page.open_form(record)
                finally:
                    QDialog.exec = original_exec
        window.close()
        # INI settings stay in the capture directory; never show a saved real email.
        login = LoginWindow(QSettings(str(output / "capture-login.ini"), QSettings.IniFormat))
        login.resize(width, height)
        login.show()
        shot(login, f"{prefix}-login")
        login.close()
        details = MovementDetailsPage()
        details.resize(width - 240, height - 56)
        details.load_movement(("M1", "PRD-009", "Monitor", "SAIDA", 1, "Confirmada",
                               "Saída demonstrativa", "23/10/2026", "—", "—", "Administrador"))
        details.show()
        shot(details, f"{prefix}-movement-details")
        details.close()
    # A fake client avoids initializing Supabase Auth just to capture a dialog.
    recovery = PasswordRecoveryDialog(client=object())
    recovery.show()
    shot(recovery, "password-recovery")
    recovery.close()
    (output / "manifest.txt").write_text("\n".join(manifest) + "\n")
    print(f"{len(manifest)} screenshots: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    capture(parser.parse_args().output)
