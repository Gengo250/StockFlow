"""Repositório de auditoria remoto via Supabase com garantia de imutabilidade (US24)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from stockflow.application.ports.audit_repository import AuditRepository
from stockflow.domain.audit_event import AuditEvent
from stockflow.domain.exceptions.audit_errors import AuditImmutabilityError


class SupabaseAuditRepository(AuditRepository):
    """Implementação do repositório de auditoria que persiste em tabela remota via Supabase."""

    def __init__(self, client, company_id: str | None = None):
        self._client = client
        self._company_id = company_id

    def record(self, event: AuditEvent) -> AuditEvent:
        """Persiste um evento na tabela de auditoria (audit_log)."""
        payload: dict[str, Any] = {
            "id": event.id,
            "user_id": event.user,
            "action": event.action,
            "entity": event.entity,
            "entity_id": event.entity_id,
            "old_values": dict(event.old_values) if event.old_values is not None else None,
            "new_values": dict(event.new_values) if event.new_values is not None else None,
            "is_critical": event.is_critical,
            "created_at": event.occurred_at.isoformat(),
        }
        if self._company_id:
            payload["company_id"] = self._company_id

        res = self._client.table("audit_log").insert(payload).execute()
        if hasattr(res, "error") and res.error:
            raise RuntimeError(f"Erro ao inserir auditoria no Supabase: {res.error}")
        return event

    def get_by_id(self, event_id: str) -> AuditEvent | None:
        """Busca evento por ID."""
        query = self._client.table("audit_log").select("*").eq("id", event_id)
        if self._company_id:
            query = query.eq("company_id", self._company_id)
        res = query.execute()
        rows = getattr(res, "data", None) or []
        if not rows:
            return None
        return self._row_to_event(rows[0])

    def list_events(
        self,
        entity: str | None = None,
        entity_id: str | None = None,
        user: str | None = None,
    ) -> Sequence[AuditEvent]:
        """Consulta eventos ordenados por data decrescente."""
        query = self._client.table("audit_log").select("*")
        if self._company_id:
            query = query.eq("company_id", self._company_id)
        if entity:
            query = query.eq("entity", entity)
        if entity_id:
            query = query.eq("entity_id", entity_id)
        if user:
            query = query.ilike("user_id", f"%{user}%")

        query = query.order("created_at", desc=True)
        res = query.execute()
        rows = getattr(res, "data", None) or []
        return tuple(self._row_to_event(r) for r in rows)

    @staticmethod
    def _row_to_event(row: dict) -> AuditEvent:
        created_at = row.get("created_at")
        if isinstance(created_at, str):
            occurred_at = datetime.fromisoformat(created_at)
        elif isinstance(created_at, datetime):
            occurred_at = created_at
        else:
            occurred_at = datetime.now(timezone.utc)

        return AuditEvent(
            id=str(row.get("id")),
            user=str(row.get("user_id")),
            action=str(row.get("action")),
            entity=str(row.get("entity")),
            entity_id=str(row.get("entity_id")),
            occurred_at=occurred_at,
            old_values=row.get("old_values"),
            new_values=row.get("new_values"),
            is_critical=bool(row.get("is_critical", False)),
        )

    def update(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser editados.")

    def delete(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser excluídos.")

    def remove(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser excluídos.")

    def clear(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser excluídos.")
