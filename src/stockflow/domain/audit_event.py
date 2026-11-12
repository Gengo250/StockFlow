"""Modelo imutável de evento de auditoria (US24)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from stockflow.domain.exceptions.audit_errors import (
    AuditImmutabilityError,
    AuditValidationError,
)


def _freeze_mapping(data: Any) -> Any:
    """Converte dicionários recursivamente em MappingProxyType para garantir imutabilidade profunda."""
    if isinstance(data, dict):
        return MappingProxyType({k: _freeze_mapping(v) for k, v in data.items()})
    if isinstance(data, (list, tuple)):
        return tuple(_freeze_mapping(v) for v in data)
    return data


@dataclass
class AuditEvent:
    """Registro imutável de evento de auditoria.

    Cada evento registra obrigatoriamente:
    - user: quem realizou a operação
    - occurred_at: data e hora (em UTC) de quando a operação ocorreu
    - action: ação executada
    - entity: tipo da entidade afetada
    - entity_id: identificador da entidade afetada

    Opcionalmente, preserva estado anterior e novo:
    - old_values: estado anterior da entidade (quando aplicável)
    - new_values: estado novo da entidade (quando aplicável)
    - is_critical: sinaliza se a operação é crítica para efeito de política de falha
    - metadata: informações adicionais de contexto (IP, tenant/company_id, etc.)
    - id: identificador único do evento (UUID)
    """

    user: str
    action: str
    entity: str
    entity_id: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    old_values: Mapping[str, Any] | None = None
    new_values: Mapping[str, Any] | None = None
    is_critical: bool = False
    metadata: Mapping[str, Any] | None = None
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        # Validação dos campos obrigatórios
        if not self.user or not str(self.user).strip():
            raise AuditValidationError("O usuário responsável é obrigatório.")
        if not self.action or not str(self.action).strip():
            raise AuditValidationError("A ação do evento é obrigatória.")
        if not self.entity or not str(self.entity).strip():
            raise AuditValidationError("A entidade do evento é obrigatória.")
        if not self.entity_id or not str(self.entity_id).strip():
            raise AuditValidationError("O identificador da entidade é obrigatório.")

        # Garantir timezone UTC para occurred_at
        if self.occurred_at is None:
            object.__setattr__(self, "occurred_at", datetime.now(timezone.utc))
        elif self.occurred_at.tzinfo is None:
            object.__setattr__(self, "occurred_at", self.occurred_at.replace(tzinfo=timezone.utc))

        # Congelamento profundo de dicionários internos
        if self.old_values is not None:
            object.__setattr__(self, "old_values", _freeze_mapping(dict(self.old_values)))
        if self.new_values is not None:
            object.__setattr__(self, "new_values", _freeze_mapping(dict(self.new_values)))
        if self.metadata is not None:
            object.__setattr__(self, "metadata", _freeze_mapping(dict(self.metadata)))

        # Bloqueia qualquer alteração posterior
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, key: str, value: Any) -> None:
        if getattr(self, "_frozen", False):
            raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser alterados.")
        super().__setattr__(key, value)

    def __delattr__(self, key: str) -> None:
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser excluídos.")
