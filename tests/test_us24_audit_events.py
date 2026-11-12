"""Testes de integração e contrato da história US24: Registrar eventos imutáveis de auditoria."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from stockflow.application.services.audit_service import AuditService
from stockflow.domain.audit_event import AuditEvent
from stockflow.domain.enums.audit_policy import AuditFailurePolicy
from stockflow.domain.exceptions.audit_errors import AuditImmutabilityError
from stockflow.infrastructure.repositories.demo_audit_repository import DemoAuditRepository
from stockflow.infrastructure.repositories.supabase_audit_repository import SupabaseAuditRepository
from stockflow.presentation import backend

ROOT = Path(__file__).resolve().parents[1]
TABLES_SQL = ROOT / "database/code/tables/12_audit_log.sql"
TRIGGERS_SQL = ROOT / "database/code/triggers/10_audit_log_immutable.sql"
POLICIES_SQL = ROOT / "database/code/policies/01_security.sql"
MIGRATION_SQL = ROOT / "database/supabase/migrations/20261112100000_us24_immutable_audit_events.sql"


# =====================================================================
# 1. TESTES DO REPOSITÓRIO DEMO
# =====================================================================


def test_demo_repository_registra_e_recupera_eventos():
    repo = DemoAuditRepository()
    ev1 = AuditEvent(
        user="ana",
        action="CREATE",
        entity="Client",
        entity_id="cli-1",
        occurred_at=datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
    )
    ev2 = AuditEvent(
        user="carlos",
        action="UPDATE",
        entity="Product",
        entity_id="prd-1",
        occurred_at=datetime(2026, 11, 12, 11, 0, tzinfo=timezone.utc),
    )

    repo.record(ev1)
    repo.record(ev2)

    # Ordenado por data decrescente
    eventos = repo.list_events()
    assert len(eventos) == 2
    assert eventos[0].id == ev2.id
    assert eventos[1].id == ev1.id

    # Busca por ID
    assert repo.get_by_id(ev1.id) == ev1
    assert repo.get_by_id("inexistente") is None

    # Filtros
    produtos = repo.list_events(entity="Product")
    assert len(produtos) == 1
    assert produtos[0].entity_id == "prd-1"

    por_usuario = repo.list_events(user="ana")
    assert len(por_usuario) == 1
    assert por_usuario[0].user == "ana"


def test_demo_repository_rejeita_qualquer_edicao_ou_exclusao():
    repo = DemoAuditRepository()
    ev = AuditEvent(user="u", action="A", entity="E", entity_id="1")
    repo.record(ev)

    with pytest.raises(AuditImmutabilityError, match="não podem ser editados"):
        repo.update(ev.id)

    with pytest.raises(AuditImmutabilityError, match="não podem ser excluídos"):
        repo.delete(ev.id)

    with pytest.raises(AuditImmutabilityError, match="não podem ser excluídos"):
        repo.remove(ev.id)

    with pytest.raises(AuditImmutabilityError, match="não podem ser excluídos"):
        repo.clear()


# =====================================================================
# 2. TESTES DO REPOSITÓRIO SUPABASE (MOCK)
# =====================================================================


def test_supabase_repository_insere_e_rejeita_edicao():
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_insert = MagicMock()
    mock_response = MagicMock()
    mock_response.error = None

    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_insert.execute.return_value = mock_response

    repo = SupabaseAuditRepository(mock_client, company_id="comp-123")
    ev = AuditEvent(
        user="admin@test.com",
        action="UPDATE_ROLE",
        entity="User",
        entity_id="usr-99",
        old_values={"role": "SELLER"},
        new_values={"role": "ADMIN"},
        is_critical=True,
    )

    gravado = repo.record(ev)
    assert gravado == ev

    # Verifica chamada de inserção
    mock_client.table.assert_called_with("audit_log")
    chamada = mock_table.insert.call_args[0][0]
    assert chamada["user_id"] == "admin@test.com"
    assert chamada["action"] == "UPDATE_ROLE"
    assert chamada["entity"] == "User"
    assert chamada["entity_id"] == "usr-99"
    assert chamada["old_values"] == {"role": "SELLER"}
    assert chamada["new_values"] == {"role": "ADMIN"}
    assert chamada["is_critical"] is True
    assert chamada["company_id"] == "comp-123"

    # Rejeição de mutações
    with pytest.raises(AuditImmutabilityError):
        repo.update(ev.id)

    with pytest.raises(AuditImmutabilityError):
        repo.delete(ev.id)


# =====================================================================
# 3. TESTES DE CONTRATO SQL (Schema declarativo e triggers)
# =====================================================================


def test_contrato_sql_tabela_audit_log_declara_campos_obrigatorios():
    source = TABLES_SQL.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS public.audit_log" in source
    assert "user_id text NOT NULL" in source
    assert "action text NOT NULL" in source
    assert "entity text NOT NULL" in source
    assert "entity_id text NOT NULL" in source
    assert "old_values jsonb" in source
    assert "new_values jsonb" in source
    assert "is_critical boolean NOT NULL DEFAULT false" in source
    assert "created_at timestamptz NOT NULL DEFAULT now()" in source


def test_contrato_sql_trigger_impede_update_e_delete():
    source = TRIGGERS_SQL.read_text(encoding="utf-8")
    assert "trg_prevent_audit_modification" in source
    assert "RAISE EXCEPTION 'Registros de auditoria são imutáveis e não podem ser editados ou excluídos'" in source
    assert "BEFORE UPDATE OR DELETE ON public.audit_log" in source


def test_contrato_sql_policies_e_migration():
    sec_source = POLICIES_SQL.read_text(encoding="utf-8")
    assert "ALTER TABLE public.audit_log       ENABLE ROW LEVEL SECURITY;" in sec_source
    assert "audit_log_select" in sec_source
    assert "audit_log_insert" in sec_source

    mig_source = MIGRATION_SQL.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS public.audit_log" in mig_source
    assert "trg_audit_log_immutable" in mig_source


# =====================================================================
# 4. TESTES DE CONFIGURAÇÃO NO BACKEND (Fabricas)
# =====================================================================


def test_backend_fabrica_audit_repository_e_service(monkeypatch):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    repo = backend.build_audit_repository()
    assert isinstance(repo, DemoAuditRepository)

    svc = backend.build_audit_service(policy=AuditFailurePolicy.FAIL_ON_CRITICAL)
    assert isinstance(svc, AuditService)
    assert svc.policy == AuditFailurePolicy.FAIL_ON_CRITICAL
