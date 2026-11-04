"""Percorre o executável uv/--mock, com rede bloqueada e configurações isoladas."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[2]
HOOK = r'''
import json, os, socket, sys, traceback
from pathlib import Path
from decimal import Decimal
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

output = Path(os.environ['STOCKFLOW_REVIEW_OUTPUT'])
network_attempts = []
def forbidden(*args, **kwargs):
    network_attempts.append(True)
    raise AssertionError('Tentativa de rede durante o modo mock')
socket.socket.connect = forbidden
socket.create_connection = forbidden
original_exec = QApplication.exec

def short_exec(self):
    evidence = {'command': 'uv run --offline --frozen stockflow --mock'}
    def exercise():
        try:
            from stockflow.presentation.windows.login_window import LoginWindow
            from stockflow.presentation.windows.main_window import MainWindow
            from stockflow.presentation.widgets.cash_register_dialog import CashRegisterDialog
            from stockflow.presentation.widgets.sale_receipt_dialog import SaleReceiptDialog
            from stockflow.presentation.backend import using_supabase
            assert not using_supabase()
            login = next(w for w in self.topLevelWidgets() if isinstance(w, LoginWindow))
            self.processEvents()
            (output / 'screenshots').mkdir(exist_ok=True)
            login.grab().save(str(output / 'screenshots/login.png'))
            login.demo_button.click()
            main = next(w for w in self.topLevelWidgets() if isinstance(w, MainWindow))
            main.resize(1366, 900)
            visited = []
            for key in main.page_widgets:
                assert main.show_page(key), key
                self.processEvents()
                visited.append(key)
            main.show_page('vendas')
            dialog = CashRegisterDialog(main.cash_register_service, main)
            dialog.refresh()
            dialog.show()
            self.processEvents()
            dialog.grab().save(str(output / 'screenshots/caixa-abertura.png'))
            dialog.initial_balance.setValue(50)
            dialog.action_button.click()
            assert main.cash_register_service.current()
            dialog.hide()
            page = main.vendas_page
            assert page.selecionar_cliente_externo('Ana Ferreira')
            assert page.selecionar_produto('PRD-009')
            page.qtd_input.setText('1')
            page.pagamento_combo.setCurrentIndex(page.pagamento_combo.findData('PIX'))
            stock_before = int(main.products['PRD-009'].stock)
            page.save_button.click()
            assert int(main.products['PRD-009'].stock) == stock_before - 1, page.warning_label.text()
            self.processEvents()
            main.grab().save(str(output / 'screenshots/venda-concluida.png'))
            sale = main.sale_repository.list_all()[0]
            receipt = main.receipt_service.issue(main.session, sale['id'])
            receipt_dialog = SaleReceiptDialog(receipt, main)
            receipt_dialog.show()
            self.processEvents()
            receipt_dialog.grab().save(str(output / 'screenshots/comprovante.png'))
            receipt_dialog.export_pdf(str(output / 'comprovante-demo.pdf'))
            receipt_dialog.close()
            dialog.refresh()
            dialog.declared['dinheiro'].setValue(50)
            dialog.declared['pix'].setValue(float(receipt.net))
            dialog.action_button.click()
            assert main.cash_register_service.current() is None
            assert 'Diferença: R$ 0,00' in dialog.feedback.text()
            dialog.show()
            self.processEvents()
            dialog.grab().save(str(output / 'screenshots/caixa-fechado.png'))
            dialog.close()
            main.show_page('relatorios')
            reports = main.reports_page
            counts = {}
            for kind in ('estoque','vendas','movimentacoes','auditoria'):
                reports.kind.setCurrentIndex(reports.kind.findData(kind))
                reports.refresh()
                assert reports.rows
                reports.export_csv(output / (kind + '.csv'))
                counts[kind] = len(reports.rows)
            self.processEvents()
            main.grab().save(str(output / 'screenshots/relatorio-auditoria.png'))
            assert 'supabase' not in sys.modules
            assert not network_attempts
            evidence.update(passed=True, backend='demo', pages=visited,
                csv_rows=counts, sold_quantity=1, net=str(receipt.net),
                cash_difference='0.00', network_attempts=len(network_attempts),
                supabase_imported=False)
            main.close()
        except BaseException:
            evidence.update(passed=False, error=traceback.format_exc())
        finally:
            (output/'smoke-cli.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+'\n')
            self.quit()
    QTimer.singleShot(0, exercise)
    return original_exec()
QApplication.exec = short_exec
'''

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='stockflow-smoke-') as scratch:
        path = Path(scratch)
        (path / 'sitecustomize.py').write_text(HOOK)
        environment = {
            **os.environ, 'PYTHONPATH': f'{path}:{ROOT / "src"}',
            'STOCKFLOW_REVIEW_OUTPUT': str(OUTPUT),
            'STOCKFLOW_BACKEND': 'supabase',  # --mock deve prevalecer
            'QT_QPA_PLATFORM': 'offscreen', 'QT_QPA_PLATFORMTHEME': '',
            'QT_STYLE_OVERRIDE': 'Fusion', 'XDG_CONFIG_HOME': str(path / 'config'),
            'XDG_CACHE_HOME': str(path / 'cache'), 'UV_CACHE_DIR': str(path / 'uv-cache'),
        }
        result = subprocess.run(['uv','run','--offline','--frozen','stockflow','--mock'],
            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60)
        (OUTPUT / 'smoke-cli.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr
        evidence = json.loads((OUTPUT / 'smoke-cli.json').read_text())
        assert evidence['passed'], evidence.get('error')
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
