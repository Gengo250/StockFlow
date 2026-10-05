"""Aceite real pelo Qt e releitura independente do Supabase.

Credenciais apenas por entrada oculta; registros próprios, marcados e
inativados no finally. Nunca executa DDL ou altera cadastros preexistentes.
"""
import getpass
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'src'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['STOCKFLOW_BACKEND'] = 'supabase'

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QInputDialog, QLineEdit, QMessageBox, QPushButton
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.infrastructure.database.supabase_client import get_client
from stockflow.presentation.windows.login_window import LoginWindow
from stockflow.presentation.windows.main_window import MainWindow
from stockflow.presentation.workers import executar_agora

OUT = Path('/tmp/stockflow-audit-20261005')
OUT.mkdir(parents=True, exist_ok=True)
MARK = '__AUDIT_20261005_' + uuid4().hex[:8]
report = {'marker': MARK, 'checks': [], 'test_records': {}, 'cleanup': []}
app = QApplication.instance() or QApplication([])
messages, slot_errors = [], []
for method in ('critical', 'warning', 'information'):
    setattr(QMessageBox, method, lambda *a, **k: messages.append('UI apresentou aviso'))
sys.excepthook = lambda typ, value, tb: slot_errors.append(value)


def persist():
    (OUT / 'remote-authenticated.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


def error_code(error):
    return str(getattr(error, 'code', type(error).__name__))


def record(name, function):
    try:
        result = function()
        item = {'check': name, 'result': 'PASS'}
        if result is not None:
            item['evidence'] = result
    except Exception as error:
        item = {'check': name, 'result': 'FAIL', 'error': error_code(error)}
        if isinstance(error, AssertionError):
            item['detail'] = str(error)
        elif error_code(error) in ('42703', 'PGRST205', 'PGRST202'):
            # Erros de metadados: somente nomes de objetos, nunca linhas ou JWT.
            item['detail'] = getattr(error, 'message', '')
    report['checks'].append(item)
    persist()
    print(json.dumps(item, ensure_ascii=False), flush=True)
    return item['result'] == 'PASS'


def assert_equal(actual, expected, message):
    assert actual == expected, message


def click(button):
    slot_errors.clear()
    button.click()
    app.processEvents()
    if slot_errors:
        raise slot_errors.pop(0)


def dialog_input(button, values):
    failures = []
    def fill():
        try:
            modal = QApplication.activeModalWidget()
            assert isinstance(modal, QDialog), 'Formulário não abriu'
            fields = modal.findChildren(QLineEdit)
            for field, value in zip(fields, values):
                field.setText(value)
            modal.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
        except Exception as error:
            failures.append(error)
            if QApplication.activeModalWidget():
                QApplication.activeModalWidget().reject()
    QTimer.singleShot(0, fill)
    click(button)
    if failures:
        raise failures[0]


def main():
    email = getpass.getpass('E-mail da conta de teste (entrada oculta): ')
    password = getpass.getpass('Senha (entrada oculta): ')
    login = LoginWindow(QSettings(str(OUT / 'live-login.ini'), QSettings.IniFormat))
    sessions = []
    login.authenticated.connect(sessions.append)
    login.email_input.setText(email)
    login.password_input.setText(password)
    del password, email
    if not record('Login pelos campos e botão reais da interface', lambda: (
        click(login.submit_button),
        assert_equal(len(sessions), 1, 'Login não produziu sessão de domínio; verificar credencial/vínculo/empresa')
    ) and None):
        login.password_input.clear()
        login.close()
        return 1
    session = sessions[0]
    report['role'] = str(session.role)
    print('Papel da conta: ' + str(session.role), flush=True)
    client = get_client()
    window = None
    product_id = supplier_id = product_code = created_category = None
    attempted_supplier = attempted_product = False
    try:
        def read_table(table, columns):
            result = client.table(table).select(columns).eq('company_id', session.company_id).limit(1).execute()
            return {'consulta_executada': True}
        for table, cols in (
            ('products', 'id,barcode,name,stock,supplier_id'),
            ('categories', 'id,name'),
            ('stock_movements', 'id,supplier_id,status'),
            ('suppliers', 'id,name,active'),
            ('clients', 'id,name,active'),
            ('sales', 'id,total'),
        ):
            record('Leitura autenticada de ' + table, lambda t=table,c=cols: read_table(t,c))
        record('products sem a coluna nova de fornecedor', lambda: read_table('products', 'id,barcode,stock'))
        record('stock_movements sem a coluna nova de fornecedor', lambda: read_table('stock_movements', 'id,kind,quantity,status'))
        for function in ('fn_list_company_users', 'fn_list_company_suppliers', 'fn_list_company_clients'):
            record('Consulta autenticada ' + function,
                   lambda f=function: {'consulta_executada': client.rpc(f, {'p_company_id': session.company_id}).execute() is not None})
        record('View real de alertas com código', lambda: {
            'consulta_executada': client.table('vw_stock_alerts').select('product_code,current_balance,min_quantity,state').eq('company_id', session.company_id).limit(1).execute() is not None})

        def open_window():
            nonlocal window
            window = MainWindow(session)
            window.executar_em_segundo_plano = executar_agora
            window.show()
            app.processEvents()
            return {'catalogo_lido': True}
        if not record('Abrir janela principal com repositórios reais', open_window):
            return 1

        def supplier_row():
            rows = client.table('suppliers').select('id,name,active').eq('company_id', session.company_id).eq('name', MARK + '_FORNECEDOR').execute().data
            return rows[0] if rows else None
        def create_supplier():
            nonlocal supplier_id, attempted_supplier
            window.show_page('fornecedores')
            attempted_supplier = True
            dialog_input(window.suppliers_page.new_supplier_button, [MARK + '_FORNECEDOR', '', '', '', 'Auditoria automatizada'])
            row = supplier_row()
            assert row, 'Fornecedor criado na interface não foi encontrado no banco'
            supplier_id = row['id']
            report['test_records']['supplier_id'] = supplier_id
            assert row['active'] is True
        if not record('Cadastrar fornecedor pela interface e reler do banco', create_supplier):
            return 1

        def product_row():
            rows = client.table('products').select('id,barcode,name,stock,sell_price,buy_price,active,supplier_id').eq('company_id', session.company_id).eq('barcode', product_code).execute().data
            return rows[0] if rows else None
        def create_first_category():
            """Primeira categoria da empresa, pela mesma porta do usuário.

            Sem nenhuma categoria o cadastro de produto é impossível pela
            tela — foi o que interrompeu a execução anterior. A categoria
            fica marcada, mas NÃO é removida na limpeza: o aplicativo não
            tem remoção de categoria, e apagar por fora seria DDL/escrita
            direta fora do que este roteiro se propõe.
            """
            nonlocal created_category
            click(window.products_page.new_product_button)
            page = window.novo_produto_page
            if page.category_input.count() > 1:
                return {'categoria_preexistente_usada': True}
            nome = MARK + '_CATEGORIA'
            QInputDialog.getText = staticmethod(lambda *a, **k: (nome, True))
            assert window._cadastrar_categoria(page) == nome, 'A interface não cadastrou a categoria'
            created_category = nome
            rows = client.table('categories').select('id,name').eq('company_id', session.company_id).eq('name', nome).execute().data
            assert rows, 'Categoria criada na interface não foi encontrada no banco'
            report['test_records']['category_id'] = rows[0]['id']
            return {'categoria_criada_pela_ui': True}
        if not record('Cadastrar a primeira categoria da empresa pela interface', create_first_category):
            return 1

        def create_product():
            nonlocal product_code, product_id, attempted_product
            page = window.novo_produto_page
            assert page.category_input.count() > 1, 'Empresa não tem categoria selecionável para criar produto pela UI'
            page.name_input.setText(MARK + '_PRODUTO')
            page.category_input.setCurrentIndex(1)
            page.sale_price_input.setValue(12.34)
            page.cost_price_input.setValue(5.67)
            page.initial_stock_input.setValue(0)
            page.minimum_stock_input.setValue(2)
            page.supplier_input.setCurrentIndex(page.supplier_input.findData(supplier_id))
            product_code = page.code_input.text()
            assert product_code and page.code_input.isReadOnly(), 'SKU deve ser gerado pelo app'
            attempted_product = True
            click(page.save_button)
            row = product_row()
            assert row, 'Produto enviado pela UI não apareceu em nova consulta'
            product_id = row['id']
            report['test_records'].update(product_id=product_id, product_code=product_code)
            assert row['name'] == MARK + '_PRODUTO'
            assert row['stock'] == 0 and float(row['sell_price']) == 12.34
            assert row['supplier_id'] == supplier_id
        if not record('Cadastrar produto pela UI com SKU automático e reler do banco', create_product):
            return 1

        def stock_value():
            return product_row()['stock']
        def edit_product():
            window._show_edit_product(window.products[product_code])
            page = window.editar_produto_page
            page.name_input.setText(MARK + '_EDITADO')
            page.sale_price_input.setValue(23.45)
            click(page.save_button)
            row = product_row()
            assert row['name'] == MARK + '_EDITADO' and float(row['sell_price']) == 23.45
        record('Editar produto pela interface e reler nome/preço', edit_product)

        def check_minimum(value):
            row = client.table('product_stock').select('min_quantity').eq('product_id', product_id).execute().data
            assert row and row[0]['min_quantity'] == value
        record('Estoque mínimo persistido', lambda: check_minimum(2))
        def check_alert(present):
            rows = client.table('vw_stock_alerts').select('product_code').eq('company_id', session.company_id).eq('product_code', product_code).execute().data
            assert bool(rows) is present
        record('Produto zerado com mínimo aparece na view real', lambda: check_alert(True))

        def toggle(active):
            row = next(p for p in window.estoque_page.produtos if p[0] == product_code)
            assert bool(window.products[product_code].active) is not active
            window.estoque_page.toggle_product_status(row)
            assert product_row()['active'] is active
        record('Inativar produto pela tabela e reler do banco', lambda: toggle(False))
        record('Inativo sai da view real de alertas', lambda: check_alert(False))
        record('Reativar produto pela tabela e reler do banco', lambda: toggle(True))

        def set_minimum(value):
            window._show_edit_product(window.products[product_code])
            page = window.editar_produto_page
            page.minimum_stock_input.setValue(value)
            click(page.save_button)
        record('Mínimo zero difere de ausente', lambda: (set_minimum(0), check_minimum(0), check_alert(True)) and None)
        record('Sem mínimo remove alerta', lambda: (set_minimum(-1), check_minimum(None), check_alert(False)) and None)
        set_minimum(2)

        def register_movement(kind, qty, confirm):
            window.show_page('movimentacoes')
            page = window.movimentacoes_page
            page.reload_products(window.products)
            page.produto_combo.setCurrentIndex(page.produto_combo.findData(product_code))
            page.especie_combo.setCurrentIndex(page.especie_combo.findData(kind))
            if kind == MovementKind.ENTRADA:
                page.fornecedor_combo.setCurrentIndex(page.fornecedor_combo.findData(supplier_id))
            page.quantidade_input.setValue(qty)
            page.nota_input.setText(MARK)
            click(page.registrar_confirmar_button if confirm else page.registrar_button)
        def movements():
            return client.table('stock_movements').select('id,kind,quantity,status,created_by,supplier_id').eq('product_id', product_id).execute().data
        def pending_entry():
            register_movement(MovementKind.ENTRADA, 5, False)
            rows = movements()
            assert len(rows) == 1 and rows[0]['status'] == 'PENDENTE'
            assert rows[0]['supplier_id'] == supplier_id and rows[0]['created_by'] == session.user_id
            assert stock_value() == 0
        record('Entrada pendente com fornecedor e autoria não altera saldo', pending_entry)
        def act_movement(movement_id, action):
            window.show_page('movimentacoes')
            page = window.movimentacoes_page
            idx = next(i for i, m in enumerate(page.movimentacoes) if m[0] == movement_id)
            buttons = page.table.cellWidget(idx, page.table.columnCount() - 1).findChildren(QPushButton)
            click(buttons[action])
        def confirm_entry():
            movement = movements()[0]
            act_movement(movement['id'], 0)
            assert stock_value() == 5
            assert window.products[product_code].stock == '5'
            assert movements()[0]['status'] == 'CONFIRMADA'
        record('Confirmar pelo botão altera banco e saldo exibido', confirm_entry)
        record('Saldo acima do mínimo sai da view de alertas', lambda: check_alert(False))

        def exit_and_cancel():
            register_movement(MovementKind.SAIDA, 2, True)
            assert stock_value() == 3
            exit_row = next(m for m in movements() if m['kind'] == 'SAIDA')
            act_movement(exit_row['id'], 1)
            assert stock_value() == 5
        record('Saída confirmada e cancelamento pela interface', exit_and_cancel)
        def excessive_exit():
            before = len(movements())
            register_movement(MovementKind.SAIDA, 6, True)
            assert stock_value() == 5 and len(movements()) == before
        record('Banco recusa saída superior ao saldo sem gravação parcial', excessive_exit)

        def fresh_catalog():
            from stockflow.infrastructure.repositories.supabase_product_repository import SupabaseProductRepository
            fresh = SupabaseProductRepository(client, session.company_id, session.role).load_catalog()
            assert fresh[product_code].stock == '5'
            assert fresh[product_code].name == MARK + '_EDITADO'
            assert fresh[product_code].supplier_id == supplier_id
        record('Novo repositório relê os valores persistidos sem cache da janela', fresh_catalog)
        return 0
    finally:
        # Descobrir criações parciais pelo marcador exclusivo, mesmo se a UI
        # lançou antes de devolver o id; nunca selecionar cadastros existentes.
        try:
            if attempted_supplier and supplier_id is None:
                rows = client.table('suppliers').select('id').eq('company_id', session.company_id).eq('name', MARK + '_FORNECEDOR').execute().data
                supplier_id = rows[0]['id'] if rows else None
            if attempted_product and product_id is None and product_code:
                rows = client.table('products').select('id,name').eq('company_id', session.company_id).eq('barcode', product_code).execute().data
                if rows and rows[0]['name'].startswith(MARK):
                    product_id = rows[0]['id']
            if product_id:
                rows = client.table('stock_movements').select('id,kind,status').eq('product_id', product_id).execute().data
                # Desfazer saídas antes das entradas evita violar stock >= 0.
                for row in sorted(rows, key=lambda r: r['kind'] != 'SAIDA'):
                    if row['status'] != 'CANCELADA':
                        client.rpc('fn_cancel_movement', {'p_movement_id': row['id']}).execute()
                client.rpc('fn_set_product_active', {'p_product_id': product_id, 'p_active': False}).execute()
                check = client.table('products').select('stock,active').eq('id', product_id).execute().data[0]
                assert check['stock'] == 0 and check['active'] is False
                report['cleanup'].append('Produto de auditoria inativo, saldo zero, movimentações canceladas')
                report['test_records']['product_id'] = product_id
            if supplier_id:
                client.rpc('fn_set_supplier_active', {'p_supplier_id': supplier_id, 'p_active': False}).execute()
                check = client.table('suppliers').select('active').eq('id', supplier_id).execute().data[0]
                assert check['active'] is False
                report['cleanup'].append('Fornecedor de auditoria inativo')
                report['test_records']['supplier_id'] = supplier_id
            if created_category:
                report['cleanup'].append(
                    'Categoria ' + created_category + ' PERMANECE: o aplicativo não remove categoria. '
                    'Para apagar, rode no SQL Editor: '
                    "DELETE FROM public.categories WHERE name = '" + created_category + "';")
            if not attempted_supplier and not attempted_product:
                report['cleanup'].append('Nenhuma gravação de cadastro ou movimentação foi tentada; não há registros para limpar')
        except Exception as error:
            report['cleanup'].append('Falha na limpeza: ' + error_code(error))
        try:
            client.auth.sign_out()
            report['cleanup'].append('Sessão de teste encerrada')
        except Exception as error:
            report['cleanup'].append('Falha no sign_out: ' + error_code(error))
        if window:
            window.close()
        login.close()
        persist()
        print(json.dumps({'cleanup': report['cleanup']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        code = main()
    except Exception as error:
        report['unexpected_error'] = error_code(error)
        persist()
        print('Interrompido com erro: ' + error_code(error), flush=True)
        code = 1
    raise SystemExit(code or int(any(c['result'] == 'FAIL' for c in report['checks'])))
