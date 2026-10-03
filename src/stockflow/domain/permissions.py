"""Políticas de permissão da aplicação, espelhando as funções do banco.

Cada política abaixo nomeia a função SQL que é a sua fonte da verdade.
Qualquer divergência aqui faz a UI liberar uma ação que o banco recusa — ou,
pior, esconder da aplicação uma regra que só o banco conhece.

- Produto: `database/code/procedures/05_catalog.sql`, que exige
  `fn_has_role(company_id, ARRAY['ADMIN','STOCK'])` para criar/editar.
- Usuário: `database/code/procedures/03_users.sql`, que exige
  `fn_is_admin(...)` em criar, editar, ativar/desativar e LISTAR.

As duas regras NÃO são a mesma: o estoquista escreve no catálogo, mas não
gerencia usuários. Reaproveitar uma lista no lugar da outra é o erro que os
testes de política existem para pegar.
"""

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError

PRODUCT_WRITE_ROLES: frozenset[UserRole] = frozenset({UserRole.ADMIN, UserRole.STOCK})

# `fn_is_admin` não tem lista: ou o papel na empresa é ADMIN, ou a função
# levanta `insufficient_privilege`. Esta é a tradução literal disso.
USER_MANAGEMENT_ROLES: frozenset[UserRole] = frozenset({UserRole.ADMIN})


def _papel_de(role_or_session) -> UserRole | None:
    """Normaliza a entrada das políticas em um `UserRole` ou `None`.

    Aceita `UserRole`, string de papel ou qualquer objeto com `.role`. Não
    importa `Session` de propósito: a entidade é que depende da política, e
    não o contrário.

    Devolve `None` para sessão ausente e para papel desconhecido — os dois
    casos em que a resposta precisa ser negar.
    """
    if role_or_session is None:
        return None
    role = getattr(role_or_session, "role", role_or_session)
    try:
        return UserRole.from_value(role)
    except ValueError:
        # Papel desconhecido nunca vira permissão: na dúvida, nega.
        return None


def can_manage_products(role_or_session) -> bool:
    """Quem pode cadastrar/editar produto: espelha `fn_has_role`."""
    return _papel_de(role_or_session) in PRODUCT_WRITE_ROLES


def ensure_can_manage_products(session, action: str = "gerenciar produtos") -> None:
    """Levanta `PermissionDeniedError` se a sessão não puder escrever produtos.

    `session is None` também é negado: sessão ausente é usuário não
    autenticado, e falhar aberto aqui deixaria a tela de estoque gravável
    para qualquer um.
    """
    if not can_manage_products(session):
        raise PermissionDeniedError(action, getattr(session, "role", None))


def can_manage_users(role_or_session) -> bool:
    """Quem pode administrar usuários: espelha `fn_is_admin`.

    Inclui LISTAR. `fn_list_company_users` recusa o não-admin, então a tela
    inteira de usuários é privilégio de ADMIN — e não só os seus botões.
    """
    return _papel_de(role_or_session) in USER_MANAGEMENT_ROLES


def ensure_can_manage_users(session, action: str = "gerenciar usuários") -> None:
    """Levanta `PermissionDeniedError` se a sessão não for de um ADMIN.

    Mesma regra de falha fechada do caminho de produto: sem sessão, nega.
    """
    if not can_manage_users(session):
        raise PermissionDeniedError(action, getattr(session, "role", None))
