"""Políticas de permissão da aplicação, espelhando as funções do banco.

Cada política abaixo nomeia a função SQL que é a sua fonte da verdade.
Qualquer divergência aqui faz a UI liberar uma ação que o banco recusa — ou,
pior, esconder da aplicação uma regra que só o banco conhece.

- Produto: `database/code/procedures/05_catalog.sql`, que exige
  `fn_has_role(company_id, ARRAY['ADMIN','STOCK'])` para criar/editar.
- Usuário: `database/code/procedures/03_users.sql`, que exige
  `fn_is_admin(...)` em criar, editar, ativar/desativar e LISTAR.
- Movimentação: `database/code/procedures/04a_movements.sql`, que exige
  `fn_has_role(company_id, ARRAY['ADMIN','STOCK'])` em registrar, confirmar
  e cancelar.

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

# Mesma lista de produto, e intencionalmente uma constante SEPARADA. As duas
# coincidem hoje porque movimentar estoque e editar catálogo são a mesma
# alçada; se um dia o vendedor puder lançar saída de venda, só esta muda.
# Reaproveitar `PRODUCT_WRITE_ROLES` faria essa mudança vazar para o catálogo.
MOVEMENT_ROLES: frozenset[UserRole] = frozenset({UserRole.ADMIN, UserRole.STOCK})

SUPPLIER_MANAGEMENT_ROLES: frozenset[UserRole] = frozenset(
    {UserRole.ADMIN, UserRole.STOCK}
)


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


def can_move_stock(role_or_session) -> bool:
    """Quem pode registrar, confirmar ou cancelar movimentação.

    Espelha o `fn_has_role(p_company_id, ARRAY['ADMIN','STOCK'])` que as três
    funções de movimentação checam antes de qualquer gravação.
    """
    return _papel_de(role_or_session) in MOVEMENT_ROLES


def ensure_can_move_stock(session, action: str = "movimentar o estoque") -> None:
    """Levanta `PermissionDeniedError` se a sessão não puder movimentar.

    Mesma falha fechada dos demais caminhos: sem sessão, nega. Movimentação
    altera saldo, e saldo é o número que decide reposição e venda.
    """
    if not can_move_stock(session):
        raise PermissionDeniedError(action, getattr(session, "role", None))


def can_manage_suppliers(role_or_session) -> bool:
    """Quem pode consultar e manter fornecedores: ADMIN e STOCK."""
    return _papel_de(role_or_session) in SUPPLIER_MANAGEMENT_ROLES


def ensure_can_manage_suppliers(
    session, action: str = "gerenciar fornecedores"
) -> None:
    """Negação fechada para sessão ausente e papéis sem alçada."""
    if not can_manage_suppliers(session):
        raise PermissionDeniedError(action, getattr(session, "role", None))


CLIENT_WRITE_ROLES = frozenset({UserRole.ADMIN, UserRole.SELLER})


def can_manage_clients(role_or_session) -> bool:
    return _papel_de(role_or_session) in CLIENT_WRITE_ROLES


def ensure_can_manage_clients(session, action="gerenciar clientes") -> None:
    if not can_manage_clients(session):
        raise PermissionDeniedError(action, getattr(session, "role", None))


def ensure_can_register_sales(session) -> None:
    ensure_can_manage_clients(session, action="registrar vendas")
