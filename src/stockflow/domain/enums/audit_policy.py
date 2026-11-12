"""Políticas para tratamento de falhas na gravação de auditoria (US24)."""

from enum import Enum


class AuditFailurePolicy(str, Enum):
    """Política definida para falhas na persistência de auditoria.

    - FAIL_ON_CRITICAL: Falhas no registro de operações críticas abortam a execução
      lançando CriticalAuditFailureError. Operações normais apenas registram aviso.
    - FAIL_ALWAYS: Toda falha de auditoria impede a continuação da operação.
    - LOG_ONLY: Falhas são logadas sem interromper a execução do chamador.
    """

    FAIL_ON_CRITICAL = "FAIL_ON_CRITICAL"
    FAIL_ALWAYS = "FAIL_ALWAYS"
    LOG_ONLY = "LOG_ONLY"
