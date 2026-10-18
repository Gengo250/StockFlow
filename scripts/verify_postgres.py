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
    sale.save_button.click()
    check(not sale.warning_label.text(), 'Qt checkout returned no error: '+sale.warning_label.text())
    check(admin.execute('SELECT count(*),sum(total) FROM sales').fetchone()==(1,__import__('decimal').Decimal('20.00')),'Qt sale persisted at catalog price and reread independently')
    # US10: venda virou cabeçalho + itens, e concluí-la baixa o estoque por
    # movimentação. As duas coisas são conferidas por conexão independente
    # porque é justamente o que um teste com cliente falso não alcança.
    sale_id=admin.execute('SELECT id FROM sales').fetchone()[0]
    check(admin.execute('SELECT count(*),sum(subtotal) FROM sale_items WHERE sale_id=%s',(sale_id,)).fetchone()==(1,__import__('decimal').Decimal('20.00')),'Sale header carries its item')
    check(admin.execute("SELECT status FROM sales WHERE id=%s",(sale_id,)).fetchone()[0]=='CONCLUIDA','Sale is closed by fn_checkout_sale')
    sale.reload_sales()
    check(sale.last_error is None and sale.historico_vendas[0]['total']=='20.00', 'Qt rereads persisted history with its embedded items')
    check(admin.execute('SELECT count(*) FROM sales_log WHERE sale_id=%s',(sale_id,)).fetchone()[0]==1,'Closing the sale stamps sales_log')
    check(admin.execute("SELECT kind,quantity,status FROM stock_movements WHERE sale_id=%s",(sale_id,)).fetchone()==('SAIDA',1,'CONFIRMADA'),'Closing the sale registers a confirmed outflow linked to it')
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==2,'Sale reduced the balance through the movement')
    client=clients[0]
    window.clientes_page.service.set_active(client.client_id,False)
    rejects(lambda:rpc('fn_register_sale',p_company_id=company,p_client_id=client.client_id,p_product_id=product_id,p_total='1'),'23503','SQL refuses inactive client')
    window.clientes_page.service.set_active(client.client_id,True)
    rejects(lambda:rpc('fn_register_sale',p_company_id=company,p_client_id=client.client_id,p_product_id=product_id,p_total='NaN'),'23514','SQL refuses NaN total')
    # US10: vender exige ter o que entregar. A conferência é do gatilho de
    # conclusão, e a venda inteira volta atrás.
    rejects(lambda:rpc('fn_create_complete_sale',p_company_id=company,p_client_id=client.client_id,p_items=[{'product_id':product_id,'quantity':999}]),'23514','SQL refuses a sale larger than the balance')
    check(admin.execute('SELECT count(*) FROM sales').fetchone()[0]==1,'Refused sale leaves no header behind')
    movement=window.movement_service.register(session,MovementInput(code,MovementKind.SAIDA,1))
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==2,'Pending movement does not change stock')
    window._confirmar_movimentacao(movement)
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==1,'Qt confirmation changes balance')
    window._cancelar_movimentacao(movement)
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==2,'Qt cancellation restores balance')
    rejects(lambda:rpc('fn_register_movement',p_company_id=company,p_product_id=product_id,p_kind='SAIDA',p_quantity=4,p_confirm=True),'23514','SQL refuses negative balance atomically')
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==2,'Rejected movement leaves balance intact')
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
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==0,'Concurrent final stock remains consistent')

    # US05: login resolves company and role only for an ACTIVE link. The app
    # denies the account here, not in the screens: fn_my_companies feeds the
    # session, so an empty result is what stops an inactive account.
    with connect('seller_auth') as seller:
        check(len(PostgresAPI(seller).rpc('fn_my_companies',{}).execute().data)==1,'Active account resolves its company at login')
    admin.execute('UPDATE company_users SET active=false WHERE company_id=%s AND user_account_id=%s',(company,ids['seller']))
    with connect('seller_auth') as seller:
        check(PostgresAPI(seller).rpc('fn_current_user_id',{}).execute().data is not None,'Deactivated account still resolves its identity')
        check(len(PostgresAPI(seller).rpc('fn_my_companies',{}).execute().data)==0,'Deactivated account gets no company: login denied')
        rejects(lambda:PostgresAPI(seller).rpc('fn_register_sale',{'p_company_id':company,'p_client_id':client.client_id,'p_product_id':product_id,'p_total':'1'}).execute(),'42501','Deactivated account cannot operate')
    admin.execute('UPDATE company_users SET active=true WHERE company_id=%s AND user_account_id=%s',(company,ids['seller']))
    with connect('seller_auth') as seller:
        check(len(PostgresAPI(seller).rpc('fn_my_companies',{}).execute().data)==1,'Reactivated account logs in again')

    # H11: manual stock adjustment. This runs BEFORE the H14 block, which
    # promotes the STOCK account to ADMIN — an adjustment checked after that
    # would no longer be measuring the STOCK role.
    #
    # What only Postgres decides: the role check inside the function, the
    # justification CHECK, the stale-balance refusal, and above all that the
    # resulting balance equals the counted one when read from OUTSIDE the
    # transaction that wrote it. `admin` is that independent connection.
    #
    # The concurrent-withdrawal scenario above drains this product to 0, and
    # p_counted_balance can never be negative. Top it back up with a plain
    # confirmed ENTRADA so `before` has real headroom for before-3, before-4
    # and before+99 below — a gap in this test's setup, not a schema rule to
    # relax.
    rpc('fn_register_movement',p_company_id=company,p_product_id=product_id,p_kind='ENTRADA',p_quantity=10,p_confirm=True)
    before=admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]
    rpc('fn_register_adjustment',p_company_id=company,p_product_id=str(product_id),
        p_counted_balance=before-3,p_expected_balance=before,p_reason='QUEBRA',
        p_detail='caixa amassada')
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==before-3,
          'Adjustment leaves the balance exactly at the counted value')
    check(admin.execute('SELECT kind,quantity,status,adjustment_reason,counted_balance '
                        'FROM stock_movements WHERE product_id=%s '
                        'ORDER BY created_on DESC LIMIT 1',(product_id,)).fetchone()
          ==('SAIDA',3,'CONFIRMADA','QUEBRA',before-3),
          'Adjustment is a confirmed movement carrying reason and counted balance')
    check(admin.execute('SELECT created_by FROM stock_movements WHERE product_id=%s '
                        'ORDER BY created_on DESC LIMIT 1',(product_id,)).fetchone()[0]==ids['user'],
          'Adjustment records the authenticated user, never a caller-supplied id')
    rejects(lambda:rpc('fn_register_adjustment',p_company_id=company,p_product_id=str(product_id),
                       p_counted_balance=before-4,p_expected_balance=before-3,
                       p_reason='OUTRO',p_detail=None),
            '23514','Reason OUTRO without a written justification is refused')
    rejects(lambda:rpc('fn_register_adjustment',p_company_id=company,p_product_id=str(product_id),
                       p_counted_balance=before-3,p_expected_balance=before-3,
                       p_reason='CONTAGEM',p_detail=None),
            '23514','Counting the same balance registers nothing')
    rejects(lambda:rpc('fn_register_adjustment',p_company_id=company,p_product_id=str(product_id),
                       p_counted_balance=1,p_expected_balance=before+99,
                       p_reason='CONTAGEM',p_detail=None),
            '40001','A balance that moved since the count asks for a recount')
    with connect('seller_auth') as seller:
        rejects(lambda:PostgresAPI(seller).rpc('fn_register_adjustment',
                    {'p_company_id':company,'p_product_id':str(product_id),
                     'p_counted_balance':0,'p_expected_balance':before-3,
                     'p_reason':'PERDA','p_detail':None}).execute(),
                '42501','A seller cannot adjust stock')
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==before-3,
          'Every refused adjustment left the balance untouched')

    # H09: chronological price/cost history. Runs BEFORE the H14 block for
    # the same reason as H11 -- that block promotes the STOCK account to
    # ADMIN, and a role check measured after it would prove nothing.
    rpc('fn_update_products',p_product_id=str(product_id),p_sell_price=31,p_buy_price=12)
    rpc('fn_update_products',p_product_id=str(product_id),p_sell_price=33)
    historico=rpc('fn_list_price_edits',p_company_id=company)
    check(len(historico)>=3,'The price history returns one row per edited field')
    check([l['changed_on'] for l in historico]==sorted((l['changed_on'] for l in historico),reverse=True),
          'The price history answers newest first')
    check(historico[0]['field']=='SELL_PRICE' and str(historico[0]['new_price']) in ('33','33.00'),
          'The most recent edit heads the list')
    # The two rows written by the same UPDATE share last_updated_on to the
    # microsecond: now() is constant inside a transaction. What the id
    # tie-break buys is not a "more recent" between them -- there is none --
    # but that the screen does not shuffle them between loads.
    assinatura=lambda linhas:[(l['field'],str(l['old_price']),str(l['new_price'])) for l in linhas]
    check(len({l['changed_on'] for l in historico if str(l['new_price']) in ('31','31.00','12','12.00')})==1,
          'Price and cost edited in one UPDATE share the same instant')
    check(assinatura(rpc('fn_list_price_edits',p_company_id=company))==assinatura(historico),
          'Two rows written in the same UPDATE keep a stable order between calls')
    check(all(l['product_code'] and l['changed_by'] for l in historico),
          'Every row resolves the product code and the author name')
    check(rpc('fn_list_price_edits',p_company_id=company,p_product_id=str(product_id))==historico,
          'Filtering by the edited product returns that product history')

    # The fixture product was born with a cost, so the first-time case needs
    # a product that was not: it is the row the original NOT NULL rejected.
    sem_custo=rpc('fn_create_products',p_company_id=company,p_barcode='NO-COST',
                  p_name='Produto sem custo',p_sell_price=10)
    rpc('fn_update_products',p_product_id=str(sem_custo),p_buy_price=7)
    primeira=rpc('fn_list_price_edits',p_company_id=company,p_product_id=str(sem_custo))
    check(len(primeira)==1 and primeira[0]['field']=='BUY_PRICE',
          'Defining a cost for the first time is audited')
    check(primeira[0]['old_price'] is None,
          'A first-time cost reaches the query as absence, not zero')
    # The screen, not just the function. A fake Supabase client cannot catch
    # a translation that asks the catalogue repository for a uuid it does not
    # carry -- that is exactly how the filtered page shipped empty.
    window._carregar_historico_precos()
    page=window.historico_precos_page
    total=page.table.rowCount()
    check(total>0,'Qt price history opens with rows')
    page.produto_combo.setCurrentIndex(page.produto_combo.findData(code))
    filtradas=page.table.rowCount()
    check(filtradas>0,'Qt price history still lists rows when filtered by one product')
    check(filtradas<=total,'Filtering never widens the result')
    check(all(page.table.item(l,1).text().startswith(code) for l in range(filtradas)),
          'Every filtered row belongs to the chosen product')
    page.produto_combo.setCurrentIndex(page.produto_combo.findData(None))
    check(page.table.rowCount()==total,'Going back to all products restores the full list')

    for papel in ('stock_auth','seller_auth'):
        with connect(papel) as outro:
            rejects(lambda c=outro: PostgresAPI(c).rpc('fn_list_price_edits',
                        {'p_company_id':company,'p_product_id':None}).execute(),
                    '42501',papel.split('_')[0].upper()+' cannot read the price history')

    # H14: profiles and permissions. Authorship on business writes, and a
    # history for every permission event. These run LAST because they change
    # roles, and an earlier check reading a mutated role would measure
    # something else.
    rpc('fn_create_supplier',p_company_id=company,p_name='Fornecedor integração')
    for table in ('products','categories','clients','suppliers'):
        author=admin.execute(f'SELECT count(*) FROM {table} WHERE created_by=%s',(ids['user'],)).fetchone()[0]
        check(author>0,f'{table} records the authenticated user who created the row')
    # role_before IS NULL marks the creation of a link, so this counts links
    # and not total events: the US05 section above already deactivated and
    # reactivated the seller, and the trigger recorded both.
    check(admin.execute('SELECT count(*) FROM role_change_log WHERE company_id=%s AND role_before IS NULL',
                        (company,)).fetchone()[0]==3,'Every company link was recorded when created')
    # Those US05 rows are the proof that the audit does not depend on going
    # through a function: a plain UPDATE on company_users is recorded too.
    check(admin.execute('SELECT count(*) FROM role_change_log WHERE target_user_id=%s AND role_before IS NOT NULL',
                        (ids['seller'],)).fetchone()[0]==2,'A direct UPDATE on the link is audited as well')
    # Promoting someone is the operation this story is about. The target is
    # the STOCK account, never the last ADMIN: keep_admin would abort instead.
    rpc('fn_save_company_member',p_company_id=company,p_user_id=str(ids['stock']),
        p_email='stock@local.invalid',p_name='Estoquista',p_role='ADMIN',p_department='')
    check(admin.execute('SELECT actor_id,role_before,role_after FROM role_change_log WHERE target_user_id=%s '
                        'ORDER BY changed_on DESC LIMIT 1',(ids['stock'],)).fetchone()==(ids['user'],'STOCK','ADMIN'),
          'Role assignment records actor, previous role and new role')
    rpc('fn_toggle_company_user',p_user_id=str(ids['seller']),p_company_id=company,p_active=False)
    check(admin.execute('SELECT actor_id,active_before,active_after FROM role_change_log WHERE target_user_id=%s '
                        'ORDER BY changed_on DESC LIMIT 1',(ids['seller'],)).fetchone()==(ids['user'],True,False),
          'Deactivating through another door is recorded too')
    before=admin.execute('SELECT count(*) FROM role_change_log').fetchone()[0]
    rpc('fn_set_company_user_department',p_company_id=company,p_user_id=str(ids['stock']),p_department='Compras')
    check(admin.execute('SELECT count(*) FROM role_change_log').fetchone()[0]==before,
          'Changing only the department is not a permission event')
    check(connection.execute('SELECT count(*) FROM role_change_log').fetchone()[0]>0,'ADMIN reads its own company audit')
    with connect('seller_auth') as seller:
        check(seller.execute('SELECT count(*) FROM role_change_log').fetchone()[0]==0,'Non-admin cannot read the audit')
    rejects(lambda:connection.execute('INSERT INTO role_change_log(company_id,target_user_id,role_after,active_after) '
                                      'VALUES (%s,%s,%s,%s)',(company,ids['user'],'ADMIN',True)),
            '42501','Not even an ADMIN writes the audit by hand')

    window.close()
    connection.close()
    admin.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--schema',action='store_true',help='Build database/code instead of migrations')
    args=parser.parse_args()
    dsn=os.environ.get('STOCKFLOW_TEST_DSN','host=127.0.0.1 port=55439 dbname=postgres user=postgres')
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
                    # Sem transação externa aqui: o PostgreSQL já executa a
                    # string inteira do arquivo numa transação implícita, e
                    # envolver de novo brigaria com a migration que abre a
                    # própria (BEGIN/COMMIT no arquivo, como o `db push` exige).
                    setup.execute(path.read_text())
                print(f'PASS {len(files)} SQL files applied; PostgreSQL {setup.info.server_version}',flush=True)
            exercise(target)
        finally:
            control.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


if __name__=='__main__':
    main()
