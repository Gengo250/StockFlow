"""Papéis de usuário, espelhando o enum `public.user_role` do banco."""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    STOCK = "STOCK"
    SELLER = "SELLER"

    @classmethod
    def from_value(cls, value):
        """Converte texto ou enum em `UserRole`.

        A UI recebe o papel como string de configuração/sessão, em caixa
        qualquer. Normalizar aqui evita que "admin" seja tratado como papel
        desconhecido e caia silenciosamente na negação de permissão.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Papel de usuário inválido: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Papel de usuário desconhecido: {value!r}") from None
