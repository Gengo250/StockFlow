"""Sessão do usuário autenticado."""

from dataclasses import dataclass

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.permissions import can_manage_products, can_manage_users


@dataclass(frozen=True)
class Session:
    user_id: str
    name: str
    email: str
    role: UserRole
    company_id: str | None = None

    @property
    def can_manage_products(self) -> bool:
        # Delega para a política: a lista de papéis tem um único dono, para
        # que mudar o SQL não exija caçar cópias da regra pelo código.
        return can_manage_products(self.role)

    @property
    def can_manage_users(self) -> bool:
        # Regra diferente da de produto (só ADMIN, como `fn_is_admin`), pelo
        # mesmo motivo delegada: a sessão não repete a lista de papéis.
        return can_manage_users(self.role)
