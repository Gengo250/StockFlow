"""Gera comprovantes demo e cenários de diagramação, sem rede ou escrita de vendas."""
import os
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile

os.environ['STOCKFLOW_BACKEND'] = 'demo'
scratch = tempfile.TemporaryDirectory(prefix='stockflow-receipt-layout-')
os.environ['XDG_CONFIG_HOME'] = scratch.name

from PySide6.QtWidgets import QApplication
from stockflow.domain.sale_receipt import ReceiptItem, ReceiptPayment
from stockflow.presentation.demo_accounts import conta_admin
from stockflow.presentation.widgets.sale_receipt_dialog import SaleReceiptDialog
from stockflow.presentation.windows.main_window import MainWindow

app = QApplication([])
window = MainWindow(conta_admin().session())
sale = next(row for row in window.sale_repository.list_all() if row['status'] == 'CONCLUIDA')
receipt = window.receipt_service.issue(window.session, sale['id'])
output = Path(__file__).parent


def export(name, value):
    dialog = SaleReceiptDialog(value, window)
    dialog.export_pdf(str(output / name))
    dialog.close()


export('comprovante-demo.pdf', receipt)
items = tuple(ReceiptItem(
    code=f'ITEM-{index:03}',
    name=f'Produto {index:03} com descrição longa para conferir a quebra de linhas e a paginação',
    quantity=2, unit_price=Decimal('975.45'), subtotal=Decimal('1950.90'),
    discount=Decimal('25.00'), final_subtotal=Decimal('1925.90'),
) for index in range(1, 36))
gross = sum(item.subtotal for item in items)
discount = sum(item.discount for item in items)
net = gross - discount
many = replace(receipt, items=items, gross=gross, item_discount=discount,
               sale_discount=Decimal(0), total_discount=discount, net=net,
               payment=ReceiptPayment('PIX', net))
export('comprovante-35-itens.pdf', many)
large = Decimal('99999999.99')
high_items = (ReceiptItem('MAX-001', 'Produto com valor máximo para conferir legibilidade',
                         1, large, large, Decimal(0), large),)
high = replace(receipt, items=high_items, gross=large, item_discount=Decimal(0),
               sale_discount=Decimal(0), total_discount=Decimal(0), net=large,
               payment=ReceiptPayment('PIX', large))
export('comprovante-valores-altos.pdf', high)
window.close()
print('Gerados três PDFs de teste em', output)
