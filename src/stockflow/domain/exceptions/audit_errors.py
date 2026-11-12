"""Exceções da auditoria (US24)."""


class AuditError(Exception):
    """Exceção base para erros relacionados à auditoria."""


class AuditImmutabilityError(AuditError, AttributeError, TypeError):
    """Lançada quando se tenta modificar, editar ou excluir um registro de auditoria."""


class AuditValidationError(AuditError, ValueError):
    """Lançada quando os campos obrigatórios do evento de auditoria estão ausentes ou inválidos."""


class CriticalAuditFailureError(AuditError, RuntimeError):
    """Lançada quando ocorre uma falha ao persistir a auditoria de uma operação crítica."""
