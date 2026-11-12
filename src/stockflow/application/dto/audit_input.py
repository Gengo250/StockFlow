"""DTOs de entrada para auditoria (US24)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class AuditEventInput:
    """Entrada de dados para registro de um evento de auditoria."""

    user: str
    action: str
    entity: str
    entity_id: str
    old_values: Mapping[str, Any] | None = None
    new_values: Mapping[str, Any] | None = None
    is_critical: bool = False
    metadata: Mapping[str, Any] | None = None
    occurred_at: datetime | None = None
