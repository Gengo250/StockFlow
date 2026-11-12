"""Repositório de auditoria em memória (demo / testes) com garantia de imutabilidade (US24)."""

from __future__ import annotations

from typing import Sequence

from stockflow.application.ports.audit_repository import AuditRepository
from stockflow.domain.audit_event import AuditEvent
from stockflow.domain.exceptions.audit_errors import AuditImmutabilityError


class DemoAuditRepository(AuditRepository):
    """Implementação append-only em memória para o repositório de auditoria.

    Mantém os eventos em uma lista interna protegida. Nenhuma edição ou
    exclusão é suportada, garantindo conformidade com as regras de imutabilidade.
    """

    def __init__(self, seed: Sequence[AuditEvent] = ()):
        self._events: list[AuditEvent] = list(seed)

    def record(self, event: AuditEvent) -> AuditEvent:
        """Adiciona um novo evento à trilha imutável."""
        if not isinstance(event, AuditEvent):
            raise TypeError("O evento deve ser uma instância de AuditEvent.")
        self._events.append(event)
        return event

    def get_by_id(self, event_id: str) -> AuditEvent | None:
        """Busca evento pelo identificador único."""
        for ev in self._events:
            if ev.id == event_id:
                return ev
        return None

    def list_events(
        self,
        entity: str | None = None,
        entity_id: str | None = None,
        user: str | None = None,
    ) -> tuple[AuditEvent, ...]:
        """Consulta os eventos ordenados cronologicamente do mais recente para o mais antigo."""
        resultado = []
        for ev in self._events:
            if entity is not None and ev.entity.lower() != entity.lower():
                continue
            if entity_id is not None and ev.entity_id != entity_id:
                continue
            if user is not None and user.lower() not in ev.user.lower():
                continue
            resultado.append(ev)

        # Ordenar do mais recente para o mais antigo
        resultado.sort(key=lambda e: e.occurred_at, reverse=True)
        return tuple(resultado)

    def update(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser editados.")

    def delete(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser excluídos.")

    def remove(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser excluídos.")

    def clear(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser excluídos.")
