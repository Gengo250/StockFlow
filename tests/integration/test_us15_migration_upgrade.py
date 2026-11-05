"""Upgrade US15 sobre histórico COMMITADO, sem backfill ou banco remoto.

Cada caso usa um banco descartável próprio no estado imediatamente anterior à
compensação. A migration é executada com seu BEGIN/COMMIT reais, não protegida
por uma transação externa que pudesse esconder um rollback ausente no script.
"""

from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb
import pytest


ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "20261104120000_us15_cancel_pending_validation.sql"
UPGRADE = ROOT / "database/supabase/migrations/20261104130000_us15_compensating_cancellation.sql"
TABLES = (
    ("public", "company", "id"),
    ("public", "user_accounts", "id"),
    ("public", "company_users", "id"),
    ("public", "products", "id"),
    ("public", "product_stock", "product_id"),
    ("public", "sales", "id"),
    ("public", "sale_items", "id"),
    ("public", "stock_movements", "id"),
    ("public", "sale_reversals", "id"),
    ("public", "sales_log", "id"),
    ("public", "returns", "id"),
    ("public", "return_items", "id"),
    ("public", "register", "id"),
    ("public", "register_log", "id"),
    ("auth", "users", "id"),
)


def authenticate(db, data):
    """Usar dentro de uma transação; identidade/papel são locais a ela."""
    db.execute("SET LOCAL ROLE authenticated")
    db.execute(
        "SELECT set_config('request.jwt.claim.sub',%s,true)", (str(data["auth_id"]),),
    )


def seed_sale(db, data, *, linked=False, complete=True):
    sale_id, item_id = uuid4(), uuid4()
    db.execute("RESET ROLE")
    # O caso linked representa uma origem que JÁ identifica o item. Os UUIDs
    # são conhecidos antes de inserir a saída: não há UPDATE/inferência de vínculo.
    db.execute(
        "INSERT INTO public.sales "
        "(id,company_id,client_name,total,status,created_by,register_log_id) "
        "VALUES (%s,%s,'Histórico US15',40,%s,%s,%s)",
        (sale_id, data["company_id"], "CONCLUIDA" if linked else "PENDENTE",
         data["actor"], data["register_id"]),
    )
    db.execute(
        "INSERT INTO public.sale_items "
        "(id,company_id,sale_id,product_id,product_name,product_code,quantity,unit_price) "
        "SELECT %s,%s,%s,id,name,barcode,2,20 FROM public.products WHERE id=%s",
        (item_id, data["company_id"], sale_id, data["product_id"]),
    )
    if linked:
        db.execute(
            "INSERT INTO public.stock_movements "
            "(company_id,product_id,sale_id,sale_item_id,kind,quantity,status,created_by,confirmed_on) "
            "VALUES (%s,%s,%s,%s,'SAIDA',2,'CONFIRMADA',%s,now())",
            (data["company_id"], data["product_id"], sale_id, item_id, data["actor"]),
        )
        db.execute(
            "INSERT INTO public.sales_log(company_id,sale_id,created_by) VALUES (%s,%s,%s)",
            (data["company_id"], sale_id, data["actor"]),
        )
    elif complete:
        # Executa o trigger antigo de verdade, que ainda não informa sale_item_id.
        db.execute("UPDATE public.sales SET status='CONCLUIDA' WHERE id=%s", (sale_id,))
    db.execute("SET LOCAL ROLE authenticated")
    return {"sale_id": sale_id, "item_id": item_id}


@pytest.fixture
def populated_database(stock_database_factory):
    with stock_database_factory("migrations", through_migration=PREVIOUS) as target:
        with psycopg.connect(target, autocommit=True) as db:
            data = {"company_id": uuid4(), "actor": uuid4(), "auth_id": uuid4()}
            email = f"{data['actor'].hex}@local.invalid"
            with db.transaction():
                db.execute(
                    "INSERT INTO public.company(id,name) VALUES (%s,'Upgrade US15')",
                    (data["company_id"],),
                )
                db.execute("INSERT INTO auth.users(id,email) VALUES (%s,%s)", (data["auth_id"], email))
                db.execute(
                    "INSERT INTO public.user_accounts(id,name,pass_hash,auth_user_id) "
                    "VALUES (%s,%s,'$auth$local-disabled-credential',%s)",
                    (data["actor"], email, data["auth_id"]),
                )
                db.execute(
                    "INSERT INTO public.company_users(company_id,user_account_id,role) "
                    "VALUES (%s,%s,'ADMIN')", (data["company_id"], data["actor"]),
                )
                authenticate(db, data)
                register = db.execute(
                    "SELECT public.fn_start_my_register(%s,0)", (data["company_id"],),
                ).fetchone()[0]
                data["register_id"] = UUID(register["id"])
                data["product_id"] = db.execute(
                    "SELECT public.fn_create_products(%s,%s,'Produto histórico',20,p_stock=>100)",
                    (data["company_id"], uuid4().hex[:12]),
                ).fetchone()[0]
                sales = {"legacy": seed_sale(db, data)}
                sales["cancelled"] = seed_sale(db, data)
                db.execute(
                    "SELECT public.fn_cancel_sale(%s,'Cancelamento legado')",
                    (sales["cancelled"]["sale_id"],),
                )
                for name, quantity in (("partial_return", 1), ("total_return", 2)):
                    sales[name] = seed_sale(db, data)
                    db.execute(
                        "SELECT public.fn_return_partial_sale(%s,%s,'Devolução anterior',%s)",
                        (sales[name]["sale_id"], Jsonb([{
                            "sale_item_id": str(sales[name]["item_id"]), "quantity": quantity,
                        }]), uuid4()),
                    )
                sales["linked"] = seed_sale(db, data, linked=True)
                sales["pending"] = seed_sale(db, data, complete=False)
                data["sales"] = sales
            # O histórico está persistido; uma nova conexão também precisa enxergá-lo.
            with psycopg.connect(target) as observer:
                assert observer.execute("SELECT count(*) FROM public.sales").fetchone()[0] == 6
            assert db.info.transaction_status == TransactionStatus.IDLE
            assert not has_cancellation_column(db)
            assert db.execute(
                "SELECT sale_item_id,status::text FROM public.stock_movements WHERE sale_id=%s",
                (sales["legacy"]["sale_id"],),
            ).fetchall() == [(None, "CONFIRMADA")]
            assert db.execute(
                "SELECT status::text FROM public.stock_movements WHERE sale_id=%s",
                (sales["cancelled"]["sale_id"],),
            ).fetchall() == [("CANCELADA",)]
            assert db.execute("SELECT count(*) FROM public.returns WHERE status='COMPLETED'").fetchone()[0] == 2
            yield db, data


def has_cancellation_column(db):
    return db.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='stock_movements' "
        "AND column_name='cancellation_id')",
    ).fetchone()[0]


def snapshot(db):
    result = {}
    for schema, table, key in TABLES:
        expression = sql.SQL("to_jsonb(t) - 'cancellation_id'") if table == "stock_movements" else sql.SQL("to_jsonb(t)")
        rows = db.execute(sql.SQL("SELECT {} FROM {}.{} t ORDER BY {}").format(
            expression, sql.Identifier(schema), sql.Identifier(table), sql.Identifier(key),
        )).fetchall()
        result[f"{schema}.{table}"] = [row[0] for row in rows]
    return result


def catalog(db):
    """A falha não pode deixar colunas, constraints, índices, funções ou grants novos."""
    signatures = ("public.fn_cancel_sale(uuid,text)", "public.fn_process_sale_completion()")
    return {
        "columns": db.execute(
            "SELECT table_name,column_name,data_type,is_nullable,column_default "
            "FROM information_schema.columns WHERE table_schema='public' "
            "ORDER BY table_name,ordinal_position",
        ).fetchall(),
        "constraints": db.execute(
            "SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) "
            "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "
            "WHERE k.connamespace='public'::regnamespace ORDER BY c.relname,k.conname",
        ).fetchall(),
        "indexes": db.execute(
            "SELECT tablename,indexname,indexdef FROM pg_indexes "
            "WHERE schemaname='public' ORDER BY tablename,indexname",
        ).fetchall(),
        "functions": [db.execute(
            "SELECT pg_get_functiondef(%s::regprocedure)", (signature,),
        ).fetchone()[0] for signature in signatures],
        "grants": [(role, signature, db.execute(
            "SELECT has_function_privilege(%s,%s,'EXECUTE')", (role, signature),
        ).fetchone()[0]) for role in ("anon", "authenticated", "app_backend") for signature in signatures],
    }


def apply_upgrade(db):
    assert db.autocommit and db.info.transaction_status == TransactionStatus.IDLE
    try:
        db.execute(UPGRADE.read_text(encoding="utf-8"))
    except psycopg.Error:
        # A migration abriu BEGIN; restaurar a conexão após a exceção também
        # comprova que os DDLs da transação que falhou não ficaram aplicados.
        db.execute("ROLLBACK")
        raise
    assert db.info.transaction_status == TransactionStatus.IDLE


def test_upgrade_preserves_committed_data_balances_and_legacy_reversals(populated_database):
    db, _ = populated_database
    before = snapshot(db)
    apply_upgrade(db)
    assert has_cancellation_column(db)
    assert snapshot(db) == before
    assert db.execute(
        "SELECT count(*) FROM public.stock_movements WHERE cancellation_id IS NOT NULL",
    ).fetchone()[0] == 0


@pytest.mark.parametrize("name,match", [
    ("legacy", "Inconsistência"),
    ("cancelled", "Somente venda pendente ou concluída"),
    ("partial_return", "devolução registrada"),
    ("total_return", "devolução registrada"),
])
def test_old_sales_are_rejected_without_backfill_or_double_restitution(populated_database, name, match):
    db, data = populated_database
    apply_upgrade(db)
    before = snapshot(db)
    with pytest.raises(psycopg.errors.CheckViolation, match=match), db.transaction():
        authenticate(db, data)
        db.execute(
            "SELECT public.fn_cancel_sale(%s,'Tentativa após upgrade')",
            (data["sales"][name]["sale_id"],),
        )
    assert snapshot(db) == before
    assert db.execute(
        "SELECT count(*) FROM public.stock_movements WHERE cancellation_id IS NOT NULL",
    ).fetchone()[0] == 0


def test_sale_with_explicit_original_links_can_be_compensated_after_upgrade(populated_database):
    db, data = populated_database
    apply_upgrade(db)
    case = data["sales"]["linked"]
    before = snapshot(db)
    with db.transaction():
        authenticate(db, data)
        result = db.execute(
            "SELECT public.fn_cancel_sale(%s,'Vínculos explícitos')", (case["sale_id"],),
        ).fetchone()[0]
    assert result["status"] == "CANCELADA"
    after = snapshot(db)
    for table in before:
        if table not in {"public.products", "public.sales", "public.sale_reversals", "public.stock_movements"}:
            assert after[table] == before[table]
    assert after["public.sales"] == [
        {**row, "status": "CANCELADA"} if row["id"] == str(case["sale_id"]) else row
        for row in before["public.sales"]
    ]
    for table in ("public.sale_reversals", "public.stock_movements"):
        current = {row["id"]: row for row in after[table]}
        for original in before[table]:
            assert current[original["id"]] == original
        assert len(after[table]) == len(before[table]) + 1
    entry, = db.execute(
        "SELECT to_jsonb(sm) FROM public.stock_movements sm WHERE cancellation_id IS NOT NULL",
    ).fetchone()
    assert entry["sale_id"] == str(case["sale_id"])
    assert entry["sale_item_id"] == str(case["item_id"])
    assert entry["product_id"] == str(data["product_id"])
    assert entry["company_id"] == str(data["company_id"])
    assert entry["quantity"] == 2
    assert entry["kind"] == "ENTRADA" and entry["status"] == "CONFIRMADA"
    assert entry["created_by"] == str(data["actor"]) and entry["confirmed_on"] is not None
    assert entry["return_id"] is None
    cancellation_id = db.execute(
        "SELECT id FROM public.sale_reversals WHERE sale_id=%s", (case["sale_id"],),
    ).fetchone()[0]
    assert entry["cancellation_id"] == str(cancellation_id)
    assert after["public.products"][0]["stock"] == before["public.products"][0]["stock"] + 2


def test_existing_pending_sale_cancels_without_moving_stock_after_upgrade(populated_database):
    db, data = populated_database
    apply_upgrade(db)
    case = data["sales"]["pending"]
    before = snapshot(db)
    with db.transaction():
        authenticate(db, data)
        db.execute("SELECT public.fn_cancel_sale(%s,'Pendência anterior')", (case["sale_id"],))
    after = snapshot(db)
    for table in before:
        if table not in {"public.sales", "public.sale_reversals"}:
            assert after[table] == before[table]
    assert after["public.sales"] == [
        {**row, "status": "CANCELADA"} if row["id"] == str(case["sale_id"]) else row
        for row in before["public.sales"]
    ]
    assert len(after["public.sale_reversals"]) == len(before["public.sale_reversals"]) + 1
    assert db.execute(
        "SELECT count(*) FROM public.stock_movements WHERE cancellation_id IS NOT NULL",
    ).fetchone()[0] == 0


def test_new_completion_after_upgrade_records_item_links(populated_database):
    db, data = populated_database
    apply_upgrade(db)
    with db.transaction():
        authenticate(db, data)
        case = seed_sale(db, data)
    original = db.execute(
        "SELECT to_jsonb(sm) FROM public.stock_movements sm WHERE sale_id=%s",
        (case["sale_id"],),
    ).fetchone()[0]
    assert original["sale_item_id"] == str(case["item_id"])
    assert original["kind"] == "SAIDA" and original["status"] == "CONFIRMADA"
    stock = db.execute("SELECT stock FROM public.products WHERE id=%s", (data["product_id"],)).fetchone()[0]
    with db.transaction():
        authenticate(db, data)
        db.execute("SELECT public.fn_cancel_sale(%s,'Venda nova')", (case["sale_id"],))
    assert db.execute(
        "SELECT to_jsonb(sm) FROM public.stock_movements sm WHERE id=%s", (original["id"],),
    ).fetchone()[0] == original
    assert db.execute("SELECT stock FROM public.products WHERE id=%s", (data["product_id"],)).fetchone()[0] == stock + 2
    assert db.execute(
        "SELECT count(*) FROM public.stock_movements "
        "WHERE sale_id=%s AND sale_item_id=%s AND cancellation_id IS NOT NULL",
        (case["sale_id"], case["item_id"]),
    ).fetchone()[0] == 1


@pytest.mark.parametrize("mismatch", ["sale", "company"])
def test_invalid_prefilled_links_abort_upgrade_without_partial_changes(populated_database, mismatch):
    db, data = populated_database
    case = data["sales"]["legacy"]
    company = data["company_id"]
    item_id = data["sales"]["pending"]["item_id"] if mismatch == "sale" else case["item_id"]
    with db.transaction():
        if mismatch == "company":
            company = uuid4()
            db.execute("INSERT INTO public.company(id,name) VALUES (%s,'Outro tenant')", (company,))
        # O schema anterior aceita esses FKs independentes. Não desabilitar
        # triggers/constraints: é precisamente a lacuna que o upgrade deve detectar.
        db.execute(
            "INSERT INTO public.stock_movements "
            "(company_id,product_id,sale_id,sale_item_id,kind,quantity,status,created_by,confirmed_on) "
            "VALUES (%s,%s,%s,%s,'SAIDA',1,'CONFIRMADA',%s,now())",
            (company, data["product_id"], case["sale_id"], item_id, data["actor"]),
        )
    before, before_catalog = snapshot(db), catalog(db)
    with pytest.raises(psycopg.errors.CheckViolation, match="migration US15 recusada sem backfill"):
        apply_upgrade(db)
    assert db.info.transaction_status == TransactionStatus.IDLE
    assert not has_cancellation_column(db)
    assert snapshot(db) == before
    assert catalog(db) == before_catalog


def test_failure_after_ddl_rolls_back_the_whole_upgrade(populated_database):
    db, _ = populated_database
    # Colisão intencional DEPOIS dos ALTER TABLE: testa rollback real do DDL,
    # não apenas a recusa antecipada do preflight de dados inconsistentes.
    db.execute(
        "CREATE INDEX uq_stock_movements_cancellation_item ON public.stock_movements(sale_id)",
    )
    before, before_catalog = snapshot(db), catalog(db)
    with pytest.raises(psycopg.errors.DuplicateTable):
        apply_upgrade(db)
    assert not has_cancellation_column(db)
    assert snapshot(db) == before
    assert catalog(db) == before_catalog


@pytest.mark.parametrize("mode,cutoff", [
    ("invalid", None),
    ("schema", PREVIOUS),
    ("migrations", "00000000000000_missing.sql"),
])
def test_database_factory_rejects_invalid_cutoffs_without_creating_databases(
    stock_database_factory, mode, cutoff,
):
    with pytest.raises(ValueError):
        with stock_database_factory(mode, through_migration=cutoff):
            pytest.fail("Configuração inválida foi aceita")


CORRECTION = ROOT / "database/supabase/migrations/20261105120000_us15_confirmed_sales_only.sql"


def test_confirmed_only_correction_preserves_history_and_rejects_pending(populated_database):
    db, data = populated_database
    apply_upgrade(db)
    before = snapshot(db)
    grants = catalog(db)["grants"]
    db.execute(CORRECTION.read_text(encoding="utf-8"))
    assert snapshot(db) == before
    assert catalog(db)["grants"] == grants
    with pytest.raises(psycopg.errors.CheckViolation, match="concluída"), db.transaction():
        authenticate(db, data)
        db.execute("SELECT public.fn_cancel_sale(%s,'Pendência anterior')", (data["sales"]["pending"]["sale_id"],))
    assert snapshot(db) == before
    # Reaplicar apenas essa corretiva não altera dados, grants ou contrato.
    db.execute(CORRECTION.read_text(encoding="utf-8"))
    assert snapshot(db) == before and catalog(db)["grants"] == grants


def test_confirmed_only_correction_still_compensates_new_sales(populated_database):
    db, data = populated_database
    apply_upgrade(db)
    db.execute(CORRECTION.read_text(encoding="utf-8"))
    with db.transaction():
        authenticate(db, data)
        case = seed_sale(db, data)
    original = db.execute("SELECT to_jsonb(sm) FROM public.stock_movements sm WHERE sale_id=%s", (case["sale_id"],)).fetchone()[0]
    stock = db.execute("SELECT stock FROM public.products WHERE id=%s", (data["product_id"],)).fetchone()[0]
    with db.transaction():
        authenticate(db, data)
        db.execute("SELECT public.fn_cancel_sale(%s,'Venda incorreta')", (case["sale_id"],))
    assert db.execute("SELECT to_jsonb(sm) FROM public.stock_movements sm WHERE id=%s", (original["id"],)).fetchone()[0] == original
    assert db.execute("SELECT stock FROM public.products WHERE id=%s", (data["product_id"],)).fetchone()[0] == stock + 2
    assert db.execute("SELECT count(*) FROM public.stock_movements WHERE sale_id=%s AND cancellation_id IS NOT NULL", (case["sale_id"],)).fetchone()[0] == 1
