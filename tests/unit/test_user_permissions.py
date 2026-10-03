"""Só ADMIN gerencia usuários.

Espelha `database/code/procedures/03_users.sql`, onde
`fn_create_company_user`, `fn_update_company_user`, `fn_toggle_company_user` e
até `fn_list_company_users` exigem `fn_is_admin(...)` e levantam
`insufficient_privilege`. A regra é MAIS restrita que a de produto: STOCK
escreve no catálogo, mas não toca em usuário. Se a lista daqui crescer, a UI
libera uma tela que o banco recusa — inclusive a listagem.
"""

import pytest

from stockflow.domain.entities.session import Session
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.permissions import (
    PRODUCT_WRITE_ROLES,
    USER_MANAGEMENT_ROLES,
    can_manage_users,
    ensure_can_manage_users,
)


def sessao(role, user_id="u-1"):
    return Session(
        user_id=user_id,
        name="Usuário de Teste",
        email="teste@stockflow.dev",
        role=role,
        company_id="c-1",
    )


# -------------------------------------------------- política de permissão

def test_papeis_de_gestao_de_usuario_batem_com_fn_is_admin():
    assert USER_MANAGEMENT_ROLES == frozenset({UserRole.ADMIN})


def test_gestao_de_usuario_e_mais_restrita_que_escrita_de_produto():
    """Âncora das duas regras: incluir STOCK aqui por engano quebra o teste.

    `fn_has_role(..., ARRAY['ADMIN','STOCK'])` libera o catálogo para o
    estoquista; `fn_is_admin` não libera usuário para ninguém além do ADMIN.
    Copiar a lista de produto para cá é o erro que este teste pega.
    """
    assert UserRole.STOCK in PRODUCT_WRITE_ROLES
    assert UserRole.STOCK not in USER_MANAGEMENT_ROLES
    assert USER_MANAGEMENT_ROLES < PRODUCT_WRITE_ROLES


@pytest.mark.parametrize(
    "role, esperado",
    [(UserRole.ADMIN, True), (UserRole.STOCK, False), (UserRole.SELLER, False)],
)
def test_can_manage_users_cobre_os_tres_papeis(role, esperado):
    assert can_manage_users(role) is esperado
    assert can_manage_users(sessao(role)) is esperado
    assert sessao(role).can_manage_users is esperado


def test_can_manage_users_nega_sessao_ausente():
    assert can_manage_users(None) is False


@pytest.mark.parametrize("lixo", ["", "GERENTE", "root", 42, object()])
def test_can_manage_users_nega_papel_desconhecido(lixo):
    # Papel que o enum do banco não conhece nunca vira permissão.
    assert can_manage_users(lixo) is False


def test_ensure_can_manage_users_libera_admin():
    assert ensure_can_manage_users(sessao(UserRole.ADMIN)) is None


@pytest.mark.parametrize("role", [UserRole.STOCK, UserRole.SELLER])
def test_ensure_can_manage_users_nega_papel_sem_permissao(role):
    with pytest.raises(PermissionDeniedError) as exc:
        ensure_can_manage_users(sessao(role), action="gerenciar usuários")

    assert exc.value.role == role
    assert "gerenciar usuários" in str(exc.value)


def test_ensure_can_manage_users_nega_sessao_ausente():
    # Sessão ausente é usuário não autenticado: negar, nunca "falhar aberto".
    with pytest.raises(PermissionDeniedError):
        ensure_can_manage_users(None, action="gerenciar usuários")
