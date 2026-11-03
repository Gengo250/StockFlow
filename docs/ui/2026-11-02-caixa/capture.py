"""Execute da raiz: QT_QPA_PLATFORM=offscreen uv run python docs/ui/2026-11-02-caixa/capture.py"""
from pathlib import Path
from PySide6.QtWidgets import QApplication
from stockflow.presentation.windows.main_window import MainWindow
from stockflow.presentation.widgets.cash_register_dialog import CashRegisterDialog
from stockflow.presentation.demo_accounts import conta_admin
from stockflow.presentation.backend import using_supabase

if using_supabase():
    raise SystemExit('Capturas usam apenas o backend demo.')
app = QApplication([])
window = MainWindow(conta_admin().session())
window.show_page('vendas')
window.show()
app.processEvents()
out = Path(__file__).parent
window.grab().save(str(out / 'vendas.png'))
dialog = CashRegisterDialog(window.cash_register_service, window)
dialog.refresh()
dialog.show()
app.processEvents()
dialog.grab().save(str(out / 'abrir.png'))
dialog.initial_balance.setValue(100)
dialog.submit()
app.processEvents()
dialog.grab().save(str(out / 'fechar.png'))
dialog.close()
window.close()
