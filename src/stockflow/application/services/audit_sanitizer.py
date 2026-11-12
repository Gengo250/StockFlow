"""Higienização e sanitização de dados sensíveis para auditoria (US24).

Regra de negócio:
Senhas, tokens e outros dados secretos não podem ser gravados.
Critério de aceite:
Dados secretos devem ser removidos antes da persistência.
"""

from __future__ import annotations

import re
from typing import Any

# Palavras-chave ou fragmentos indicativos de dados sensíveis (em minúsculas)
DEFAULT_SENSITIVE_PATTERNS = {
    "password",
    "senha",
    "pass",
    "secret",
    "token",
    "jwt",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "auth_token",
    "private_key",
    "privkey",
    "cvv",
    "pin",
    "credential",
}


def is_sensitive_key(key: str) -> bool:
    """Verifica se o nome de um campo/chave é sensível."""
    norm = str(key).strip().lower().replace("-", "_")
    return any(p in norm for p in DEFAULT_SENSITIVE_PATTERNS)


def sanitize_sensitive_data(data: Any) -> Any:
    """Remove recursivamente chaves e dados sensíveis antes da persistência.

    Dicionários têm suas chaves sensíveis removidas completamente.
    Listas e tuplas têm seus elementos sanitizados recursivamente.
    Strings que aparentem tokens JWT ou cabeçalhos Bearer são mascaradas.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if is_sensitive_key(str(k)):
                # Conforme o critério de aceite: dados secretos são removidos antes da persistência.
                continue
            sanitized[k] = sanitize_sensitive_data(v)
        return sanitized

    if isinstance(data, list):
        return [sanitize_sensitive_data(item) for item in data]

    if isinstance(data, tuple):
        return tuple(sanitize_sensitive_data(item) for item in data)

    if isinstance(data, str):
        # Mascarar padrões de token explícitos caso apareçam em texto
        if re.search(r"Bearer\s+[A-Za-z0-9_\-\.]+", data, re.I):
            return re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", r"\1[REDACTED]", data, flags=re.I)
        return data

    return data


class AuditSanitizer:
    """Serviço responsável por sanitizar payloads antes da gravação de auditoria."""

    def __init__(self, additional_patterns: set[str] | None = None):
        self._patterns = set(DEFAULT_SENSITIVE_PATTERNS)
        if additional_patterns:
            self._patterns.update(p.lower() for p in additional_patterns)

    def sanitize(self, data: Any) -> Any:
        return sanitize_sensitive_data(data)
