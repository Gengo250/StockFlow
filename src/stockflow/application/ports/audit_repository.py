"""Porta de persistência imutável de auditoria (US24)."""

from typing import Protocol, Sequence

from stockflow.domain.audit_event import AuditEvent


class AuditRepository(Protocol):
    """Contrato de persistência imutável de eventos de auditoria.

    Registros de auditoria são estritamente de inserção única (append-only) e leitura.
    Operações de edição (update) ou exclusão (delete) não são permitidas pela aplicação
    e levantam AuditImmutabilityError caso invocadas.
    """

    def record(self, event: AuditEvent) -> AuditEvent:
        """Persiste um evento imutável de auditoria."""
        ...

    def get_by_id(self, event_id: str) -> AuditEvent | None:
        """Busca um evento de auditoria pelo identificador."""
        ...

    def list_events(
        self,
        entity: str | None = None,
        entity_id: str | None = None,
        user: str | None = None,
    ) -> Sequence[AuditEvent]:
        """Consulta eventos de auditoria cadastrados."""
        ...
