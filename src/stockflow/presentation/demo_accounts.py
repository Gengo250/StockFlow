"""Contas locais de demonstração, cada uma com o seu papel.

NÃO é autenticação de verdade: senha em texto puro no código só existe
enquanto a demonstração roda offline. O caminho real é
`fn_get_login_credentials` no banco, que devolve o hash e o papel do usuário.

O motivo de existirem três contas, e não uma, é a US01: sem um papel sem
permissão para entrar, não há como ver na tela a diferença entre quem pode e
quem não pode gravar produto — e o controle passava despercebido.
"""

import hmac
from dataclasses import dataclass

from stockflow.domain.entities.session import Session
from stockflow.domain.enums.user_role import UserRole


@dataclass(frozen=True)
class DemoAccount:
    user_id: str
    name: str
    email: str
    password: str
    role: UserRole

    def session(self) -> Session:
        return Session(
            user_id=self.user_id,
            name=self.name,
            email=self.email,
            role=self.role,
        )


DEMO_ACCOUNTS = (
    DemoAccount("USR-001", "Ana Ferreira", "ana.ferreira@example.com",
                "StockFlow123", UserRole.ADMIN),
    DemoAccount("USR-002", "Carlos Mendes", "carlos.mendes@example.com",
                "Estoque123", UserRole.STOCK),
    DemoAccount("USR-004", "Juliana Ramos", "juliana.ramos@example.com",
                "Vendas123", UserRole.SELLER),
)

DEMO_ACCOUNTS_BY_EMAIL = {account.email: account for account in DEMO_ACCOUNTS}

# Senha que não pertence a ninguém. Serve só para dar o que comparar quando o
# e-mail não existe: devolver `None` antes do `compare_digest` faria o tempo
# de resposta revelar quais e-mails estão cadastrados.
_SENHA_INEXISTENTE = "x" * 64


def _normalizar_email(email) -> str:
    return (email or "").strip().casefold()


def conta_por_email(email) -> DemoAccount | None:
    return DEMO_ACCOUNTS_BY_EMAIL.get(_normalizar_email(email))


def conta_por_papel(role) -> DemoAccount:
    """Conta de demonstração de um papel. Útil para testes e para a sessão padrão."""
    role = UserRole.from_value(role)
    for account in DEMO_ACCOUNTS:
        if account.role is role:
            return account
    raise LookupError(f"Nenhuma conta de demonstração com o papel {role}.")


def conta_admin() -> DemoAccount:
    return conta_por_papel(UserRole.ADMIN)


def autenticar(email, senha) -> Session | None:
    """Devolve a `Session` da conta ou `None` se a credencial não bater."""
    account = conta_por_email(email)
    esperada = account.password if account is not None else _SENHA_INEXISTENTE
    confere = hmac.compare_digest((senha or "").encode(), esperada.encode())
    if account is None or not confere:
        return None
    return account.session()
