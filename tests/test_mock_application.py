"""Aceite do modo mock pelo mesmo login e pelas mesmas telas do aplicativo."""

import os
import subprocess
import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox
import pytest

from stockflow.presentation.app import LoginFlow
from stockflow.presentation.demo_products import DEMO_PRODUCTS


@pytest.fixture
def demo_flow(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    def forbidden(*args, **kwargs):
        pytest.fail("O fluxo mock tentou acessar um serviço externo")

    from stockflow.presentation import backend
    monkeypatch.setattr(backend, "_client", forbidden)
    for name in ("critical", "warning"):
        monkeypatch.setattr(QMessageBox, name, lambda *args: pytest.fail(str(args[1:])))
    flow = LoginFlow(QSettings(str(tmp_path / "login.ini"), QSettings.IniFormat))
    flow.login.demo_button.click()
    assert flow.main is not None
    yield flow
    if flow.main is not None:
        flow.main.close()
    flow.login.close()


def test_mock_startup_does_not_import_supabase_or_connect(tmp_path):
    script = '''
import socket, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

def forbidden(*args, **kwargs):
    raise AssertionError("Conexão externa no modo mock")
socket.socket.connect = forbidden
from stockflow.presentation.app import run
from stockflow.presentation.windows.login_window import LoginWindow
from stockflow.presentation.windows.main_window import MainWindow
original_exec = QApplication.exec
opened = []

def short_exec(self):
    def exercise():
        try:
            login = next(w for w in self.topLevelWidgets() if isinstance(w, LoginWindow))
            login.demo_button.click()
            main = next(w for w in self.topLevelWidgets() if isinstance(w, MainWindow))
            for key in main.page_widgets:
                assert main.show_page(key), key
            opened.append(True)
            main.close()
        finally:
            self.quit()
    QTimer.singleShot(10, exercise)
    return original_exec()
QApplication.exec = short_exec
assert run(["--mock"]) == 0
assert opened == [True]
from stockflow.presentation.backend import using_supabase
assert not using_supabase()
assert "supabase" not in sys.modules
'''
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=20,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen",
             "XDG_CONFIG_HOME": str(tmp_path), "STOCKFLOW_BACKEND": "supabase"},
    )
    assert result.returncode == 0, result.stderr


def test_demo_login_opens_every_page_and_every_report(demo_flow, tmp_path):
    window = demo_flow.main
    for key, page in window.page_widgets.items():
        assert window.show_page(key), key
        assert window.pages.currentWidget() is page
    for kind in ("estoque", "vendas", "movimentacoes", "auditoria"):
        page = window.reports_page
        page.kind.setCurrentIndex(page.kind.findData(kind))
        page.refresh()
        assert page.rows, kind
        assert not page.error.text(), (kind, page.error.text())
        destination = tmp_path / f"{kind}.csv"
        page.export_csv(destination)
        assert len(destination.read_text(encoding="utf-8-sig").splitlines()) > 1
    assert window.suppliers_page.table.rowCount() > 0
    assert window.clientes_page.table.rowCount() > 0
    assert window.users_page.user_table.table.rowCount() > 0
    assert window.historico_precos_page.table.rowCount() > 0


def test_demo_sales_movements_and_catalog_are_consistent(demo_flow):
    window = demo_flow.main
    assert window.products == DEMO_PRODUCTS
    assert window.sale_repository.movements is window.movement_repository
    sales = window.sale_repository.list_all()
    assert {row["status"] for row in sales} >= {"CONCLUIDA", "CANCELADA", "DEVOLVIDA"}
    movements = window.movement_repository.list_movements()
    assert {row[5] for row in movements} >= {"Confirmada", "Pendente", "Cancelada"}
    for code, product in window.products.items():
        balance = sum((1 if row[3] == "Entrada" else -1) * row[4]
                      for row in movements if row[1] == code and row[5] == "Confirmada")
        assert balance == int(product.stock), code
    generated = [row for row in sales if row.get("client_id")]
    assert len(generated) >= 5
    for row in generated:
        assert window.client_repository.get(row["client_id"])
        assert row["seller_id"]
        assert all(item["product_code"] in window.products for item in row["items"])


def test_demo_sale_receipt_and_reversal_update_stock(demo_flow):
    window = demo_flow.main
    sale = next(row for row in window.sale_repository.list_all()
                if row.get("client_id") and row["status"] == "CONCLUIDA")
    code = sale["items"][0]["product_code"]
    quantity = sale["items"][0]["quantity"]
    stock = int(window.products[code].stock)
    receipt = window.receipt_service.issue(window.session, sale["id"])
    assert receipt
    window._cancelar_venda(sale["id"], "Cancelamento de exemplo pelo usuário")
    assert int(window.products[code].stock) == stock + quantity
    assert window.sale_repository.get(sale["id"])["status"] == "CANCELADA"


def test_new_login_recreates_demo_catalog(demo_flow):
    window = demo_flow.main
    code = "PRD-009"
    window.product_repository.set_active(code, False)
    demo_flow.logout()
    demo_flow.login.demo_button.click()
    assert demo_flow.main is not window
    assert demo_flow.main.products[code] == DEMO_PRODUCTS[code]


def test_edit_form_accepts_the_inventory_row(demo_flow):
    window = demo_flow.main
    row = window.estoque_page.produtos[0]
    window.editar_produto_page.load_product(row)
    assert window.editar_produto_page.code_input.text() == row[0]
    assert window.editar_produto_page.maximum_stock_input.value() == 0
