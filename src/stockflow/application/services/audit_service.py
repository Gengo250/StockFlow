"""Serviço central de registro de eventos imutáveis de auditoria (US24)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from stockflow.application.dto.audit_input import AuditEventInput
from stockflow.application.ports.audit_repository import AuditRepository
from stockflow.application.services.audit_sanitizer import (
    AuditSanitizer,
    sanitize_sensitive_data,
)
from stockflow.domain.audit_event import AuditEvent
from stockflow.domain.enums.audit_policy import AuditFailurePolicy
from stockflow.domain.exceptions.audit_errors import (
    AuditImmutabilityError,
    AuditValidationError,
    CriticalAuditFailureError,
)

logger = logging.getLogger(__name__)


class AuditService:
    """Serviço central para registro e controle de auditoria.

    Garante:
    - Validação dos campos obrigatórios (usuário, data/hora, ação, entidade, id).
    - Higienização e remoção de dados secretos (senhas, tokens, secrets).
    - Preservação do estado anterior e novo para alterações.
    - Imutabilidade da trilha de auditoria (sem métodos de update/delete).
    - Aplicação de política estrita de falhas para operações críticas.
    """

    def __init__(
        self,
        repository: AuditRepository,
        policy: AuditFailurePolicy = AuditFailurePolicy.FAIL_ON_CRITICAL,
        sanitizer: AuditSanitizer | None = None,
    ):
        self._repository = repository
        self._policy = policy
        self._sanitizer = sanitizer or AuditSanitizer()

    @property
    def repository(self) -> AuditRepository:
        return self._repository

    @property
    def policy(self) -> AuditFailurePolicy:
        return self._policy

    def record_event(self, data: AuditEventInput) -> AuditEvent | None:
        """Registra um evento a partir de um AuditEventInput."""
        return self.record(
            user=data.user,
            action=data.action,
            entity=data.entity,
            entity_id=data.entity_id,
            old_values=data.old_values,
            new_values=data.new_values,
            is_critical=data.is_critical,
            metadata=data.metadata,
            occurred_at=data.occurred_at,
        )

    def record(
        self,
        user: Any,
        action: str,
        entity: str,
        entity_id: str,
        old_values: Mapping[str, Any] | None = None,
        new_values: Mapping[str, Any] | None = None,
        is_critical: bool = False,
        metadata: Mapping[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditEvent | None:
        """Cria e persiste um evento de auditoria higienizado e imutável."""
        # 1. Identificação do usuário
        user_str = self._extract_user(user)

        # 2. Validação preliminar de campos obrigatórios
        if not user_str or not user_str.strip():
            raise AuditValidationError("O usuário responsável é obrigatório.")
        if not action or not str(action).strip():
            raise AuditValidationError("A ação do evento é obrigatória.")
        if not entity or not str(entity).strip():
            raise AuditValidationError("A entidade do evento é obrigatória.")
        if not entity_id or not str(entity_id).strip():
            raise AuditValidationError("O identificador da entidade é obrigatório.")

        # 3. Sanitização de segredos antes da persistência
        sanitized_old = sanitize_sensitive_data(old_values) if old_values is not None else None
        sanitized_new = sanitize_sensitive_data(new_values) if new_values is not None else None
        sanitized_meta = sanitize_sensitive_data(metadata) if metadata is not None else None

        # 4. Data e hora com fuso horário
        timestamp = occurred_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # 5. Instanciação do evento imutável
        event = AuditEvent(
            user=user_str.strip(),
            action=str(action).strip(),
            entity=str(entity).strip(),
            entity_id=str(entity_id).strip(),
            occurred_at=timestamp,
            old_values=sanitized_old,
            new_values=sanitized_new,
            is_critical=bool(is_critical),
            metadata=sanitized_meta,
        )

        # 6. Persistência e aplicação da política de falhas
        try:
            return self._repository.record(event)
        except Exception as exc:
            self._handle_failure(exc, event)
            return None

    def _handle_failure(self, exc: Exception, event: AuditEvent) -> None:
        """Trata falhas de persistência com base na criticidade e política configurada."""
        msg = (
            f"Falha ao persistir evento de auditoria [ação={event.action}, "
            f"entidade={event.entity}, id={event.entity_id}, crítica={event.is_critical}]: {exc}"
        )

        if self._policy == AuditFailurePolicy.FAIL_ALWAYS:
            raise CriticalAuditFailureError(msg) from exc

        if self._policy == AuditFailurePolicy.FAIL_ON_CRITICAL:
            if event.is_critical:
                raise CriticalAuditFailureError(msg) from exc
            logger.warning(msg)
            return

        # LOG_ONLY
        logger.warning(msg)

    @staticmethod
    def _extract_user(user: Any) -> str:
        """Extrai a identificação textual de um objeto de usuário, sessão ou string."""
        if user is None:
            return ""
        if isinstance(user, str):
            return user
        # Compatibilidade com Session e objetos de usuário do domínio
        for attr in ("name", "email", "user_id", "login"):
            val = getattr(user, attr, None)
            if val and str(val).strip():
                return str(val).strip()
        return str(user)

    def get_event(self, event_id: str) -> AuditEvent | None:
        """Recupera um evento de auditoria por ID."""
        return self._repository.get_by_id(event_id)

    def list_events(
        self,
        entity: str | None = None,
        entity_id: str | None = None,
        user: str | None = None,
    ) -> tuple[AuditEvent, ...]:
        """Consulta eventos registrados."""
        return tuple(self._repository.list_events(entity=entity, entity_id=entity_id, user=user))

    # Métodos que vedam edição ou exclusão pela aplicação
    def update(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser editados.")

    def edit(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser editados.")

    def delete(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser excluídos.")

    def remove(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser excluídos.")

    def clear(self, *args, **kwargs):
        raise AuditImmutabilityError("Registros de auditoria são imutáveis e não podem ser excluídos.")
