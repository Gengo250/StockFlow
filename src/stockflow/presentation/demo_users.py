"""Base de usuários da demonstração.

Este módulo **não define** seu próprio enum ``UserRole``. Ele importa o enum
centralizado de ``stockflow.domain.enums.user_role``.  Assim todas as partes
do código – fixtures, UI e serviços – utilizam a mesma classe de enum, evitando
o erro ``ValueError: Papel de usuário inválido`` que ocorria quando duas
definições distintas eram misturadas.
"""

from __future__ import annotations
from typing import List, Tuple

# Fonte única de dados de demonstração
from stockflow.presentation.demo_data import DEMO_PEOPLE, linhas_de_usuarios

# Enum oficial (único) – reutilizado em toda a aplicação
from stockflow.domain.enums.user_role import UserRole

# ----------------------------------------------------------------------
# Converte objetos ``DEMO_PEOPLE`` (namedtuple ou dataclass) para a tupla
# esperada pelas tabelas da UI.
# ----------------------------------------------------------------------
def _to_ui_tuple(person) -> Tuple[str, str, str, str, str, str, str]:
    """Retorna a representação de 7 campos usada pela UI antiga."""
    return (
        getattr(person, "name", ""),
        getattr(person, "login", ""),
        getattr(person, "department", ""),
        getattr(person, "role", ""),  # string – já coincide com UserRole.value
        getattr(person, "status", ""),
        getattr(person, "last_seen", ""),
        getattr(person, "color", ""),
    )

# Lista de usuários que a UI consome (tuplas).  Mantemos a ordem original.
DEMO_USERS: List[Tuple[str, str, str, str, str, str, str]] = [
    _to_ui_tuple(p) for p in DEMO_PEOPLE
]

# Perfis realmente presentes na base, preservando a ordem de aparição.
USER_ROLES: Tuple[str, ...] = tuple(
    dict.fromkeys(p.role for p in DEMO_PEOPLE)  # preserve insertion order
)

__all__ = ["UserRole", "DEMO_USERS", "USER_ROLES"]

