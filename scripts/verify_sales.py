"""Testa vendas, concorrência e conversão do schema remoto em PostgreSQL local.

Cria/remove apenas stockflow_verify_* em localhost. Nunca acessa Supabase.
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
from threading import Barrier
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from verify_postgres import BOOTSTRAP, ROOT, check, rejects
from postgres_api import PostgresAPI

# As que ainda não estão no remoto: o ensaio aplica o resto primeiro, insere
# dado histórico e só então estas. A H09 (20261015103000) precisa entrar aqui
# por dependência, não só por estar pendente: 20261014120000 recria
# `trg_log_price_edit` com CREATE OR REPLACE, então aplicá-la depois da H09
# apagaria a auditoria de custo sem erro nenhum. A 20261015143000 entra
# pela mesma corrente: ela declara uma função que devolve `price_edit_field`,
# o tipo que a 20261015103000 cria.
# A 20261016120000 entra pela mesma corrente: ela declara
# `p_payment_method public.payment_method DEFAULT 'DINHEIRO'`, e o tipo com
# esse rótulo nasce na 20261013140000, que é pendente. Aplicada no lote que
# simula o remoto, o ensaio morria em
# `invalid input value for enum payment_method: "DINHEIRO"`.
PENDING_VERSIONS = {"20261013120000", "20261013140000", "20261014120000",
                    "20261015103000", "20261015143000", "20261016120000"}


def run():
    dsn = os.environ.get("STOCKFLOW_TEST_DSN", "host=127.0.0.1 port=55439 dbname=postgres user=postgres")
    if conninfo_to_dict(dsn).get("host") not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Only a disposable local PostgreSQL server is supported.")
    with psycopg.connect(dsn, autocommit=True) as control:
        for role in ("anon", "authenticated", "service_role"):
            if not control.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                control.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        for scenario in (exercise, exercise_us07):
            name = "stockflow_verify_" + uuid4().hex[:12]
            control.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            target = make_conninfo(dsn, dbname=name)
            try:
                scenario(target)
            finally:
                control.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def exercise(dsn):
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute(BOOTSTRAP)
        files = sorted((ROOT / "database/supabase/migrations").glob("*.sql"))
        pending = PENDING_VERSIONS
        for path in files:
            if path.name[:14] not in pending:
                with db.transaction():
                    db.execute(path.read_text())
        check(db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='sales' AND column_name='customer_name'").fetchone(), "Historical migrations reproduce the remote customer_name schema")

        company, other, user, auth, seller, seller_auth, stock, stock_auth, client, product, product2, sale, log = [uuid4() for _ in range(13)]
        for cid in (company, other):
            db.execute("INSERT INTO company(id,name) VALUES (%s,'Integration company')", (cid,))
        for uid, aid, role in ((user, auth, 'ADMIN'), (seller, seller_auth, 'SELLER'), (stock, stock_auth, 'STOCK')):
            db.execute("INSERT INTO auth.users(id,email) VALUES (%s,%s)", (aid, str(uid)+'@local.invalid'))
            db.execute("INSERT INTO user_accounts(id,name,pass_hash,auth_user_id) VALUES (%s,%s,%s,%s)", (uid,str(uid),'$auth$local-disabled-credential',aid))
            db.execute("INSERT INTO company_users(company_id,user_account_id,role) VALUES (%s,%s,%s)", (company,uid,role))
        db.execute("INSERT INTO register(id,change) VALUES (%s,0)", (user,))
        db.execute("INSERT INTO clients(id,company_id,name) VALUES (%s,%s,'Legacy client')", (client,company))
        for pid, code in ((product,'SALE-1'),(product2,'SALE-2')):
            db.execute("INSERT INTO products(id,company_id,barcode,name,sell_price) VALUES (%s,%s,%s,%s,20)", (pid,company,code,code))
            db.execute("INSERT INTO stock_movements(company_id,product_id,kind,quantity,status) VALUES (%s,%s,'ENTRADA',20,'CONFIRMADA')", (company,pid))
        # COMPLETE no INSERT não dispara o trigger quebrado do remoto.
        db.execute("INSERT INTO sales(id,company_id,client_id,customer_name,total,status,created_by) VALUES (%s,%s,%s,'Historical snapshot',40,'COMPLETE',%s)", (sale,company,client,user))
        db.execute("INSERT INTO sale_items(company_id,sale_id,product_id,product_name,product_code,quantity,unit_price) VALUES (%s,%s,%s,'Old name','SALE-1',2,20)", (company,sale,product))
        db.execute("INSERT INTO sales_log(id,sale_id,created_by) VALUES (%s,%s,%s)", (log,sale,user))
        db.execute("INSERT INTO price_edit_log(company_id,product_id,old_price,new_price,updated_by) VALUES (%s,%s,10,20,%s)", (company,product,user))
        db.execute("INSERT INTO stock_movements(company_id,product_id,sale_id,kind,quantity,status) VALUES (%s,%s,%s,'SAIDA',2,'CONFIRMADA')", (company,product,sale))
        before = db.execute("SELECT id,sale_id,product_id,quantity,unit_price,subtotal,product_name FROM sale_items ORDER BY id").fetchall()
        balances = db.execute("SELECT id,stock FROM products ORDER BY id").fetchall()
        # Colunas explícitas em vez de `*`: a H09 acrescenta `field` à tabela,
        # e `SELECT *` compararia tuplas de larguras diferentes antes e depois
        # — a conversão pareceria destrutiva só por ter ganhado uma coluna.
        AUDIT = "SELECT id,company_id,product_id,old_price,new_price,updated_by FROM price_edit_log ORDER BY id"
        price_logs = db.execute(AUDIT).fetchall()

        def migrate():
            with db.transaction():
                for path in files:
                    if path.name[:14] in pending:
                        db.execute(path.read_text())

        # Recusar dado incompatível deve preservar o banco anterior inteiro.
        db.execute("UPDATE sale_items SET quantity=2.5 WHERE sale_id=%s", (sale,))
        rejects(migrate, 'P0001', 'Fractional historical quantity aborts the conversion')
        check(db.execute("SELECT quantity FROM sale_items WHERE sale_id=%s", (sale,)).fetchone()[0] == Decimal('2.5'),
              'Refused migration does not round or delete historical items')
        db.execute("UPDATE sale_items SET quantity=2 WHERE sale_id=%s", (sale,))
        # O CLI aplica uma transação por arquivo, como neste caminho.
        for path in files:
            if path.name[:14] in pending:
                with db.transaction():
                    db.execute(path.read_text())
        check(db.execute("SELECT id,sale_id,product_id,quantity,unit_price,subtotal,product_name FROM sale_items ORDER BY id").fetchall()==before, "Incremental migration preserves historical item IDs, quantities, prices and snapshots")
        check(db.execute("SELECT id,stock FROM products ORDER BY id").fetchall()==balances, "Migration does not repeat historical stock withdrawals")
        check(db.execute("SELECT client_name,total,status::text FROM sales WHERE id=%s",(sale,)).fetchone()==('Historical snapshot',Decimal('40'),'CONCLUIDA'), "Historical sale and total survive enum/column conversion")
        check(db.execute("SELECT company_id,created_by FROM sales_log WHERE id=%s",(log,)).fetchone()==(company,user), "Migration preserves existing completion logs")
        check(db.execute(AUDIT).fetchall()==price_logs, "Reconciliation preserves the historical price audit")
        check(db.execute("SELECT DISTINCT field::text FROM price_edit_log").fetchall()==[('SELL_PRICE',)],
              "Audit rows written before H09 stay readable as sell price edits")
        check(db.execute("SELECT to_regprocedure('public.fn_register_stock_entry(uuid,uuid,numeric,uuid,uuid,text)')").fetchone()[0] is None,
              "Obsolete stock entry cannot bypass the authorized movement functions")

        def connect(aid=auth):
            conn = psycopg.connect(dsn, autocommit=True)
            conn.execute("SET ROLE authenticated")
            conn.execute("SELECT set_config('request.jwt.claim.sub',%s,false)",(str(aid),))
            conn.execute("SET statement_timeout='8s'")
            return conn

        def checkout(conn, items, **extra):
            args = dict(p_company_id=str(company), p_client_id=str(client), p_items=items,
                        p_payment_method='PIX', p_discount='0')
            args.update(extra)
            return PostgresAPI(conn).rpc('fn_checkout_sale',args).execute().data

        def item(pid, quantity):
            return {'product_id':str(pid),'quantity':quantity}

        with connect(seller_auth) as conn:
            receipt = checkout(conn,[item(product,2),item(product2,3)],p_discount='5')
            check(Decimal(str(receipt['total']))==Decimal('95') and receipt['payment_method']=='PIX', "SELLER checkout returns the canonical total and payment")
            check(db.execute("SELECT stock FROM products WHERE id=%s",(product,)).fetchone()[0]==16, "Multi-item checkout deducts the requested quantity")
            check(len(receipt['sale_items'])==2, "Receipt includes both saved item snapshots")
            count = db.execute("SELECT count(*) FROM sales").fetchone()[0]
            rejects(lambda: checkout(conn,[item(product,1),item(product2,999)]),'23514', 'Insufficient stock rolls back the entire cart')
            check(db.execute("SELECT count(*) FROM sales").fetchone()[0]==count and db.execute("SELECT stock FROM products WHERE id=%s",(product,)).fetchone()[0]==16, "Refused cart leaves neither header nor partial withdrawal")
            for quantity in (0,-1,1.5,'oops',1000001):
                rejects(lambda q=quantity: checkout(conn,[item(product,q)]),'23514',f'Invalid SQL quantity {quantity} is rejected')
            rejects(lambda: checkout(conn,[item(product,1)],p_discount='0.001'),'23514','Sub-cent discount is rejected')
            rejects(lambda: checkout(conn,[item(product,1)],p_company_id=str(other)),'42501','SELLER cannot checkout for another company')
            check(conn.execute("SELECT count(*) FROM price_edit_log").fetchone()[0] == 0, 'SELLER cannot read the administrative price audit')
        with connect(stock_auth) as conn:
            rejects(lambda: checkout(conn,[item(product,1)]),'42501','STOCK cannot checkout')

        # `fn_register_sale` é a porta do desktop e a função que esta entrega
        # recria com assinatura nova. Ela recebe itens por CÓDIGO, não por id,
        # então nada do bloco de `fn_checkout_sale` acima a exercita. Os testes
        # de unidade da US012 falam com um cliente Supabase falso, que aceita
        # qualquer payload e não tem schema — é exatamente o tipo de cobertura
        # que deixou a tela de histórico de preços abrir vazia contra o banco.
        def vender(conn, itens, **extra):
            args = dict(p_company_id=str(company), p_client_id=str(client),
                        p_items=itens, p_payment_method='DINHEIRO', p_discount='0')
            args.update(extra)
            return PostgresAPI(conn).rpc('fn_register_sale', args).execute().data

        def linha(code, quantity):
            return {'product_code': code, 'quantity': quantity}

        FECHAMENTO = ("SELECT s.total, s.discount,"
                      " (SELECT sum(subtotal) FROM sale_items WHERE sale_id=s.id)"
                      " FROM sales s WHERE s.id=%s")

        with connect(seller_auth) as conn:
            antes = db.execute("SELECT stock FROM products WHERE id=%s",(product,)).fetchone()[0]
            venda = vender(conn, [linha('SALE-1',2), linha('SALE-2',1)], p_discount='5')
            check(Decimal(str(venda['total']))==Decimal('55'),
                  'Desktop multi-item sale returns the canonical total')
            check(len(venda['items'])==2, 'Desktop sale snapshots every item')
            check(db.execute("SELECT stock FROM products WHERE id=%s",(product,)).fetchone()[0]==antes-2,
                  'Desktop sale deducts the requested quantity')
            total, desconto, subtotais = db.execute(FECHAMENTO,(venda['id'],)).fetchone()
            check(subtotais - desconto == total,
                  'The stored sale reconciles: sum(subtotal) - discount = total')

            vendas_antes = db.execute("SELECT count(*) FROM sales").fetchone()[0]
            saldo_antes = db.execute("SELECT stock FROM products WHERE id=%s",(product,)).fetchone()[0]
            rejects(lambda: vender(conn,[linha('SALE-1',1), linha('SALE-2',999)]),'23514',
                    'Insufficient stock rolls back the whole desktop cart')
            check(db.execute("SELECT count(*) FROM sales").fetchone()[0]==vendas_antes
                  and db.execute("SELECT stock FROM products WHERE id=%s",(product,)).fetchone()[0]==saldo_antes,
                  'Refused desktop cart leaves neither header nor partial withdrawal')

            # Os dois limites que `fn_create_complete_sale` já exigia e que
            # esta função aceitava: desconto de sub-centavo grava uma linha que
            # não fecha, e a quantidade ia até o teto de `integer`.
            rejects(lambda: vender(conn,[linha('SALE-1',1)],p_discount='10.005'),'23514',
                    'Sub-cent discount is rejected by the desktop entry point')
            rejects(lambda: vender(conn,[linha('SALE-1',1)],p_discount='0.001'),'23514',
                    'Discount below one cent is rejected')
            rejects(lambda: vender(conn,[linha('SALE-1',1000001)]),'23514',
                    'Quantity above the shared 1000000 ceiling is rejected')
            rejects(lambda: vender(conn,[linha('NAO-EXISTE',1)]),'23503',
                    'Unknown product code is refused by code, not by a NOT NULL crash')
            rejects(lambda: vender(conn,[]),'23514','Desktop sale without items is refused')
            rejects(lambda: vender(conn,[linha('SALE-1',1)],p_company_id=str(other)),'42501',
                    'SELLER cannot register a desktop sale for another company')

        with connect(stock_auth) as conn:
            rejects(lambda: vender(conn,[linha('SALE-1',1)]),'42501',
                    'STOCK cannot register a desktop sale')

        # O critério de aceite diz "inclusive em vendas concorrentes". Duas
        # vendas disputando o último saldo: uma passa, uma é recusada, e o
        # saldo nunca fica negativo.
        # Produto próprio para a disputa: esvaziar um do fixture compartilhado
        # deixaria sem saldo o checkout Qt que roda logo abaixo.
        disputado = uuid4()
        db.execute("INSERT INTO products(id,company_id,barcode,name,sell_price)"
                   " VALUES (%s,%s,'SALE-3','SALE-3',20)", (disputado, company))
        db.execute("INSERT INTO stock_movements(company_id,product_id,kind,quantity,status)"
                   " VALUES (%s,%s,'ENTRADA',4,'CONFIRMADA')", (company, disputado))
        portao = Barrier(2)

        def disputar(_):
            with connect(seller_auth) as conn:
                portao.wait(timeout=5)
                try:
                    vender(conn, [linha('SALE-3', 4)])
                    return 'ok'
                except psycopg.Error as erro:
                    return erro.sqlstate

        with ThreadPoolExecutor(max_workers=2) as pool:
            disputa = sorted(pool.map(disputar, range(2)))
        check(disputa == ['23514','ok'],
              'Concurrent desktop sales cannot sell the same remaining stock twice')
        check(db.execute("SELECT stock FROM products WHERE id=%s",(disputado,)).fetchone()[0]==0,
              'The contested product lands exactly at zero, never below')
        with connect() as conn:
            movement = db.execute("SELECT id FROM stock_movements WHERE sale_id=%s",(receipt['id'],)).fetchone()[0]
            rejects(lambda: PostgresAPI(conn).rpc('fn_cancel_movement',{'p_movement_id':str(movement)}).execute(),'23514','A sale withdrawal cannot be cancelled independently')
            # O que a venda concluída registrou, lido ANTES de mexer no
            # catálogo. Sem esta foto, a comparação lá embaixo não prova nada.
            ITENS = ("SELECT product_name,product_code,quantity,unit_price,subtotal "
                     "FROM sale_items WHERE sale_id=%s ORDER BY product_code")
            vendido = db.execute(ITENS, (receipt['id'],)).fetchall()
            fechado = db.execute("SELECT total,discount FROM sales WHERE id=%s", (receipt['id'],)).fetchone()

            # Preço e custo no MESMO UPDATE: é o caminho que a tela usa, e é
            # onde um trigger com um IF só gravaria a mudança de custo com os
            # valores de preço. O custo deste produto nunca foi informado,
            # então esta é também a primeira definição — o caso que o
            # `old_price NOT NULL` original derrubava.
            conn.execute("SELECT public.fn_update_products(%s, p_sell_price => 25, p_buy_price => 9)", (product,))
            ULTIMA = ("SELECT updated_by,old_price,new_price FROM price_edit_log "
                      "WHERE product_id=%s AND field=%s ORDER BY last_updated_on DESC LIMIT 1")
            check(db.execute(ULTIMA, (product, 'SELL_PRICE')).fetchone()
                  == (user, Decimal('20'), Decimal('25')), 'Price audit resolves the authenticated author')
            check(db.execute(ULTIMA, (product, 'BUY_PRICE')).fetchone()
                  == (user, None, Decimal('9')), 'Cost edit is audited without inventing a previous value')
            check(db.execute("SELECT count(*) FROM price_edit_log WHERE product_id=%s", (product,)).fetchone()[0] == 3,
                  'One UPDATE touching both fields leaves one audit row per field')
            rejects(lambda: conn.execute("DELETE FROM price_edit_log"), '42501', 'Even ADMIN cannot rewrite the price audit')

            # H09, segunda metade: a venda concluída guarda os valores dela, e
            # não um ponteiro para o catálogo. A divergência é conferida antes
            # da igualdade de propósito — se o preço gravado fosse o mesmo do
            # catálogo novo, a comparação seguinte passaria sem provar nada.
            check(db.execute("SELECT sell_price FROM products WHERE id=%s", (product,)).fetchone()[0] == Decimal('25')
                  and any(linha[1] == 'SALE-1' and linha[3] == Decimal('20') for linha in vendido),
                  'The recorded unit price and the current catalogue price really diverge')
            check(db.execute(ITENS, (receipt['id'],)).fetchall() == vendido,
                  'Editing price and cost does not touch what a completed sale recorded')
            check(db.execute("SELECT total,discount FROM sales WHERE id=%s", (receipt['id'],)).fetchone() == fechado,
                  'The completed sale keeps the total it was closed with')

        with connect(seller_auth) as conn:
            exercise_ui(conn, db, company, seller, client, product)

        # Duas vendas reservam produtos em ordens inversas: sem locks
        # ordenados FOR UPDATE o código original produzia deadlock.
        barrier = Barrier(2)
        def sell_reverse(reverse):
            with connect() as conn:
                ids = [product,product2][::(-1 if reverse else 1)]
                barrier.wait(timeout=5)
                return checkout(conn,[item(pid,1) for pid in ids])['id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(sell_reverse,[False,True]))
        check(len(set(results))==2, "Concurrent reversed carts both commit without deadlock")

        remaining = db.execute("SELECT stock FROM products WHERE id=%s", (product,)).fetchone()[0]
        sales_before = db.execute("SELECT count(*) FROM sales").fetchone()[0]
        barrier = Barrier(2)

        def sell_last_stock(_):
            with connect() as conn:
                barrier.wait(timeout=5)
                try:
                    checkout(conn, [item(product, remaining)])
                    return 'ok'
                except psycopg.Error as error:
                    return error.sqlstate

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(sell_last_stock, range(2)))
        check(sorted(results) == ['23514', 'ok'], 'Concurrent checkouts cannot sell the same remaining stock twice')
        check(db.execute("SELECT count(*) FROM sales").fetchone()[0] == sales_before + 1,
              'Concurrent refused sale leaves no partial header')
        check(db.execute("SELECT count(*) FROM products p WHERE stock <> public.fn_confirmed_balance(id)").fetchone()[0]==0, "All balances reconcile with confirmed movements")

        with connect() as conn:
            conn.execute("SELECT set_config('request.jwt.claim.sub',%s,false)",(str(uuid4()),))
            check(conn.execute("SELECT count(*) FROM sales").fetchone()[0]==0, "RLS hides sales from an unaffiliated authenticated account")
        with psycopg.connect(dsn,autocommit=True) as conn:
            conn.execute('SET ROLE anon')
            rejects(lambda: checkout(conn,[item(product,1)]),'42501','Anonymous checkout is denied')
        print('PASS sales acceptance complete',flush=True)


def exercise_us07(dsn):
    """O outro estado suportado guardava o produto no cabeçalho da venda."""
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute(BOOTSTRAP)
        files = sorted((ROOT / 'database/supabase/migrations').glob('*.sql'))
        for path in files:
            if path.name[:14] < '20261010000000':
                with db.transaction():
                    db.execute(path.read_text())
        company, client, product, sale, deleted_product_sale = [uuid4() for _ in range(5)]
        db.execute("INSERT INTO company(id,name) VALUES (%s,'US07 fixture')", (company,))
        db.execute("INSERT INTO clients(id,company_id,name) VALUES (%s,%s,'Client')", (client,company))
        db.execute("INSERT INTO products(id,company_id,barcode,name,sell_price) VALUES (%s,%s,'LEGACY','Current name',20)", (product,company))
        db.execute("INSERT INTO stock_movements(company_id,product_id,kind,quantity,status) VALUES (%s,%s,'ENTRADA',10,'CONFIRMADA')", (company,product))
        for sid, pid in ((sale, product), (deleted_product_sale, None)):
            db.execute("INSERT INTO sales(id,company_id,client_id,product_id,client_name,product_name,product_code,total) "
                       "VALUES (%s,%s,%s,%s,'Old client','Old product','OLD',15)", (sid,company,client,pid))
        for path in files:
            if path.name[:14] in PENDING_VERSIONS:
                with db.transaction():
                    db.execute(path.read_text())
        rows = db.execute("SELECT product_id,product_name,product_code,quantity,unit_price,subtotal FROM sale_items ORDER BY product_id NULLS LAST").fetchall()
        check(rows == [(product, 'Old product', 'OLD', 1, Decimal('15'), Decimal('15')),
                       (None, 'Old product', 'OLD', 1, Decimal('15'), Decimal('15'))],
              'US07 conversion preserves snapshots even when the product was deleted')
        check(db.execute("SELECT stock FROM products WHERE id=%s", (product,)).fetchone()[0] == 10,
              'US07 conversion never invents a historical stock withdrawal')
        check(db.execute("SELECT count(*) FROM sales WHERE status='CONCLUIDA' AND total=15").fetchone()[0] == 2,
              'US07 historical headers retain their totals and completed state')


def exercise_ui(connection, db, company, seller, client_id, product):
    """Widgets reais, catálogo desatualizado e conferência por outra conexão."""
    from PySide6.QtWidgets import QApplication
    from stockflow.application.services.sale_service import SaleService
    from stockflow.domain.entities.session import Session
    from stockflow.domain.enums.user_role import UserRole
    from stockflow.infrastructure.repositories.supabase_client_repository import SupabaseClientRepository
    from stockflow.infrastructure.repositories.supabase_product_repository import SupabaseProductRepository
    from stockflow.infrastructure.repositories.supabase_sale_repository import SupabaseSaleRepository
    from stockflow.presentation.pages.vendas import VendasPage

    app = QApplication.instance() or QApplication([])
    api = PostgresAPI(connection)
    products = SupabaseProductRepository(api, str(company))
    catalog = products.load_catalog()
    repository = SupabaseSaleRepository(api, str(company))
    service = SaleService(repository, SupabaseClientRepository(api, str(company)), products)
    session = Session(str(seller), 'Seller local', 'seller@local.invalid', UserRole.SELLER, str(company))
    page = VendasPage(products=catalog, service=service, session=session)
    try:
        assert page._apontar_cliente(str(client_id))
        assert page.selecionar_produto('SALE-1')
        page.qtd_input.setText('2')
        page.add_button.click()
        assert page.selecionar_produto('SALE-2')
        page.qtd_input.setText('3')
        page.desconto_input.setText('5,00')
        page.pagamento_combo.setCurrentIndex(page.pagamento_combo.findData('PIX'))
        # O preço muda fora da UI antes da gravação; o recibo deve usar 30.
        db.execute("UPDATE products SET sell_price=30 WHERE id=%s", (product,))
        page.save_button.click()
        check(not page.warning_label.text(), 'Qt multi-item checkout succeeds: ' + page.warning_label.text())
        row = page.historico_vendas[0]
        check(Decimal(row['total']) == Decimal('115'), 'Qt shows the saved total despite a stale price cache')
        check(db.execute("SELECT total,payment_method::text,discount FROM sales WHERE id=%s", (row['id'],)).fetchone()
              == (Decimal('115'), 'PIX', Decimal('5')), 'Independent connection verifies Qt payment, discount and total')
        check(db.execute("SELECT sum(quantity) FROM sale_items WHERE sale_id=%s", (row['id'],)).fetchone()[0] == 5,
              'Qt direct selection is included with the existing cart')
        page.reload_sales()
        check(page.last_error is None and len(page.historico_vendas[0]['items']) == 2,
              'Reloading real history preserves both item details')
        check(len(page.table.item(0, 2).toolTip().splitlines()) == 2, 'History tooltip lists persisted quantities and names')
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == '__main__':
    run()
