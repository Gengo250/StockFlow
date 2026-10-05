"""Execute migrations or declarative schema and Qt flows in an isolated local DB.

Usage: STOCKFLOW_TEST_DSN='host=127.0.0.1 port=55439 dbname=postgres' uv run python scripts/verify_postgres.py
Creates and drops only randomly named stockflow_verify_* databases. No remote host allowed.
Supabase Auth is represented by its users table and auth.uid(); actual Auth/HTTP are not tested here.
"""
import argparse
import os
from pathlib import Path
import sys
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'/'support')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from postgres_api import PostgresAPI

BOOTSTRAP = """
CREATE SCHEMA auth;
CREATE TABLE auth.users(id uuid PRIMARY KEY, email varchar(255), raw_user_meta_data jsonb DEFAULT '{}', last_sign_in_at timestamptz);
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
GRANT USAGE ON SCHEMA auth TO authenticated, anon;
GRANT EXECUTE ON FUNCTION auth.uid() TO authenticated, anon;
"""


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print('PASS', label, flush=True)


def rejects(operation, state, label):
    try:
        operation()
    except psycopg.Error as error:
        check(error.sqlstate == state, label + ' (' + str(error.sqlstate) + ')')
    else:
        raise AssertionError(label + ': accepted unexpectedly')


def exercise(dsn):
    admin = psycopg.connect(dsn, autocommit=True)
    ids = {key: uuid4() for key in ('company', 'other', 'user', 'auth', 'seller', 'seller_auth', 'stock', 'stock_auth')}
    for company in ('company','other'):
        admin.execute('INSERT INTO company(id,name) VALUES (%s,%s)', (ids[company], company))
    for role, user, auth in [('ADMIN','user','auth'),('SELLER','seller','seller_auth'),('STOCK','stock','stock_auth')]:
        admin.execute('INSERT INTO auth.users(id,email) VALUES (%s,%s)', (ids[auth], user+'@local.invalid'))
        admin.execute('INSERT INTO user_accounts(id,name,pass_hash,auth_user_id) VALUES (%s,%s,%s,%s)', (ids[user],user+'@local.invalid','$auth$local-disabled-credential',ids[auth]))
        admin.execute('INSERT INTO company_users(company_id,user_account_id,role) VALUES (%s,%s,%s)', (ids['company'],ids[user],role))

    def connect(auth='auth'):
        conn = psycopg.connect(dsn, autocommit=True)
        conn.execute('SET ROLE authenticated')
        conn.execute("SELECT set_config('request.jwt.claim.sub', %s, false)", (str(ids[auth]),))
        return conn

    connection = connect()
    api = PostgresAPI(connection)
    rpc = lambda name, **args: api.rpc(name,args).execute().data
    company = str(ids['company'])
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox, QDialogButtonBox, QInputDialog, QLineEdit
    from stockflow.presentation import backend
    from stockflow.presentation.windows import main_window
    from stockflow.presentation.workers import executar_agora
    from stockflow.domain.entities.session import Session
    from stockflow.domain.enums.user_role import UserRole
    from stockflow.application.dto.movement_input import MovementInput
    from stockflow.domain.enums.movement_kind import MovementKind
    from stockflow.application.dto.client_input import ClientInput
    app = QApplication.instance() or QApplication([])
    errors=[]
    for name in ('critical','warning','information'):
        setattr(QMessageBox,name,lambda *args: errors.append(str(args[-1])))
    os.environ['STOCKFLOW_BACKEND']='supabase'
    backend._client=lambda:api
    main_window.executar_em_segundo_plano=executar_agora
    session=Session(user_id=str(ids['user']),name='Admin local',email='user@local.invalid',role=UserRole.ADMIN,company_id=company)
    window=main_window.MainWindow(session)
    check(not window.products,'Qt opens using empty real database')
    window._show_new_product('produtos')
    form=window.novo_produto_page
    check(form.category_input.count()==1,'Company without categories offers none')
    QInputDialog.getText=staticmethod(lambda *args,**kwargs:('Categoria teste',True))
    window._cadastrar_categoria(form)
    check(form.category_input.currentText()=='Categoria teste','Qt creates the first category of the company')
    check(admin.execute('SELECT count(*) FROM categories WHERE company_id=%s',(company,)).fetchone()[0]==1,'Category persisted and reread independently')
    form.name_input.setText('Produto integração')
    form.sale_price_input.setValue(20)
    form.cost_price_input.setValue(10)
    form.initial_stock_input.setValue(3)
    form.minimum_stock_input.setValue(3)
    form.description_input.setPlainText('Descrição persistida')
    form.ncm_input.setText('12345678')
    form.ean_input.setText('1234567890123')
    form.location_input.setText('Prateleira A')
    form.low_stock_alert.setChecked(False)
    code=form.code_input.text()
    form.save_button.click()
    check(window.last_save_error is None,'Qt saves product: '+str(window.last_save_error))
    row=admin.execute('SELECT id,stock,description,ncm,ean,location,low_stock_alert FROM products WHERE barcode=%s',(code,)).fetchone()
    check(row and row[1:] == (3,'Descrição persistida','12345678','1234567890123','Prateleira A',False),'Independent connection rereads all product fields and initial movement')
    product_id=str(row[0])
    check(len(window.product_repository.list_alerts())==1,'Alert view has barcode and correct minimum')
    window._show_edit_product(window.products[code])
    form=window.editar_produto_page
    form.description_input.setPlainText('Descrição editada')
    form.save_button.click()
    check(admin.execute('SELECT description FROM products WHERE id=%s',(product_id,)).fetchone()[0]=='Descrição editada','Qt edit persisted')

    def fill_client():
        dialog=app.activeModalWidget()
        dialog.findChildren(QLineEdit)[0].setText('Cliente integração')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
    QTimer.singleShot(0,fill_client)
    window.clientes_page.new_client_button.click()
    clients=window.client_repository.list_all()
    check(len(clients)==1,'Qt client dialog persists client')
    sale=window.vendas_page
    sale.cliente_combo.setCurrentIndex(1)
    sale.produto_combo.setCurrentIndex(1)
    sale.val_input.setText('25,90')
    sale.save_button.click()
    check(admin.execute('SELECT count(*),sum(total) FROM sales').fetchone()==(1,__import__('decimal').Decimal('25.90')),'Qt sale persisted and reread independently')
    client=clients[0]
    window.clientes_page.service.set_active(client.client_id,False)
    rejects(lambda:rpc('fn_register_sale',p_company_id=company,p_client_id=client.client_id,p_product_id=product_id,p_total='1'),'23503','SQL refuses inactive client')
    window.clientes_page.service.set_active(client.client_id,True)
    rejects(lambda:rpc('fn_register_sale',p_company_id=company,p_client_id=client.client_id,p_product_id=product_id,p_total='NaN'),'23514','SQL refuses NaN total')
    movement=window.movement_service.register(session,MovementInput(code,MovementKind.SAIDA,1))
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==3,'Pending movement does not change stock')
    window._confirmar_movimentacao(movement)
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==2,'Qt confirmation changes balance')
    window._cancelar_movimentacao(movement)
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==3,'Qt cancellation restores balance')
    rejects(lambda:rpc('fn_register_movement',p_company_id=company,p_product_id=product_id,p_kind='SAIDA',p_quantity=4,p_confirm=True),'23514','SQL refuses negative balance atomically')
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==3,'Rejected movement leaves balance intact')
    window.product_repository.set_active(code,False)
    rejects(lambda:rpc('fn_register_movement',p_company_id=company,p_product_id=product_id,p_kind='ENTRADA',p_quantity=1),'23503','SQL refuses inactive product')
    window.product_repository.set_active(code,True)
    rejects(lambda:rpc('fn_toggle_company_user',p_company_id=company,p_user_id=str(ids['user']),p_active=False),'23001','SQL preserves last active administrator')
    # Metadata constraint fires after create/minimum operations; the whole form must roll back.
    data={'code':'BROKEN','name':'Atomic failure','sale_price':'1','cost':'1','unit':'UN','stock':'2','category':'Categoria teste','ncm':'invalid'}
    rejects(lambda:rpc('fn_save_product',p_company_id=company,p_product_id=None,p_data=data),'23514','Product form rolls back on invalid metadata')
    check(admin.execute("SELECT count(*) FROM products WHERE barcode='BROKEN'").fetchone()[0]==0,'No partial product remains')
    with connect('seller_auth') as seller:
        seller_api=PostgresAPI(seller)
        rejects(lambda:seller_api.rpc('fn_save_product',{'p_company_id':company,'p_product_id':None,'p_data':data}).execute(),'42501','SELLER cannot save product')
        check(seller.execute('SELECT count(*) FROM products WHERE company_id=%s',(ids['other'],)).fetchone()[0]==0,'RLS hides other company')
        rejects(lambda:seller_api.rpc('fn_list_company_users',{'p_company_id':company}).execute(),'42501','SELLER cannot list users')
    with connect('stock_auth') as stock:
        stock_api=PostgresAPI(stock)
        rejects(lambda:stock_api.rpc('fn_create_client',{'p_company_id':company,'p_name':'Forbidden'}).execute(),'42501','STOCK cannot create client')
        rejects(lambda:stock_api.rpc('fn_register_sale',{'p_company_id':company,'p_client_id':client.client_id,'p_product_id':product_id,'p_total':'1'}).execute(),'42501','STOCK cannot register sale')

    def withdraw(_):
        with connect() as conn:
            try:
                PostgresAPI(conn).rpc('fn_register_movement',{'p_company_id':company,'p_product_id':product_id,'p_kind':'SAIDA','p_quantity':2,'p_confirm':True}).execute()
                return 'ok'
            except psycopg.Error as error:
                return error.sqlstate
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(withdraw,range(2)))
    check(sorted(results)==['23514','ok'],'Concurrent withdrawals serialize; only one fits balance')
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==1,'Concurrent final stock remains consistent')
    window.close()
    connection.close()
    admin.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--schema',action='store_true',help='Build database/code instead of migrations')
    args=parser.parse_args()
    dsn=os.environ.get('STOCKFLOW_TEST_DSN','host=127.0.0.1 port=55439 dbname=postgres')
    config=conninfo_to_dict(dsn)
    if config.get('host') not in {'127.0.0.1','localhost','::1'}:
        raise SystemExit('Only a disposable local PostgreSQL server is supported.')
    name='stockflow_verify_'+uuid4().hex[:12]
    with psycopg.connect(dsn,autocommit=True) as control:
        for role in ('anon','authenticated','service_role'):
            if not control.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                control.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        control.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        target=make_conninfo(dsn,dbname=name)
        try:
            with psycopg.connect(target,autocommit=True) as setup:
                setup.execute(BOOTSTRAP)
                files=([f for group in ('tables','procedures','views','triggers','policies') for f in sorted((ROOT/'database'/'code'/group).glob('*.sql'))]
                       if args.schema else sorted((ROOT/'database'/'supabase'/'migrations').glob('*.sql')))
                for path in files:
                    with setup.transaction():
                        setup.execute(path.read_text())
                print(f'PASS {len(files)} SQL files applied; PostgreSQL {setup.info.server_version}',flush=True)
            exercise(target)
        finally:
            control.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


if __name__=='__main__':
    main()
