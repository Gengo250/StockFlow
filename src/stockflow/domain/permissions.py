"""Política de permissão de escrita no catálogo de produtos.

Fonte da verdade: `database/code/procedures/05_catalog.sql`, que exige
`fn_has_role(company_id, ARRAY['ADMIN','STOCK'])` para criar/editar produto.
Qualquer divergência aqui faz a UI liberar uma ação que o banco recusa.
"""

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError

PRODUCT_WRITE_ROLES: frozenset[UserRole] = frozenset({UserRole.ADMIN, UserRole.STOCK})


def can_manage_products(role_or_session) -> bool:
    """Aceita `UserRole`, string de papel ou qualquer objeto com `.role`.

    Não importa `Session` de propósito: a entidade é que depende da política,
    e não o contrário.
    """
    if role_or_session is None:
        return False
    role = getattr(role_or_session, "role", role_or_session)
    try:
        role = UserRole.from_value(role)
    except ValueError:
        # Papel desconhecido nunca vira permissão: na dúvida, nega.
        return False
    return role in PRODUCT_WRITE_ROLES


def ensure_can_manage_products(session, action: str = "gerenciar produtos") -> None:
    """Levanta `PermissionDeniedError` se a sessão não puder escrever produtos.

    `session is None` também é negado: sessão ausente é usuário não
    autenticado, e falhar aberto aqui deixaria a tela de estoque gravável
    para qualquer um.
    """
    if not can_manage_products(session):
        raise PermissionDeniedError(action, getattr(session, "role", None))
