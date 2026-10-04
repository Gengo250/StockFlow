"""Diretório de usuários da empresa, lido do Supabase.

Tudo passa por `fn_list_company_users`, e não por SELECT nas tabelas: nem
`user_accounts` nem `company_users` têm GRANT de leitura para role de
aplicação nenhuma (`policies/01_security.sql` deixa as duas de fora da lista
de SELECT de propósito). O acesso a elas é sempre por função SECURITY DEFINER.

Essa função já recusa quem não é ADMIN (`fn_is_admin`), então a listagem é
restrita pelo BANCO, não só pela tela. É o mesmo desenho da US01: o controle
visual esconde, mas quem nega é a camada de baixo.
"""

from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.user_mapper import rows_to_users

PERMISSION_SQLSTATE = "42501"
PERMISSION_HINTS = (
    "apenas administradores",
    "permission denied",
    "insufficient_privilege",
)

ACTION_BY_RPC = {
    "fn_list_company_users": "abrir a administração de usuários",
    "fn_set_company_user_department": "alterar o departamento de um usuário",
}


class SupabaseUserRepository:
    def __init__(self, client, company_id, role=None):
        self._client = client
        self._company_id = company_id
        # Só nomeia o papel na mensagem de recusa; não decide nada.
        self._role = role

    def list_users(self, agora=None) -> tuple:
        """Usuários da empresa nas tuplas que a tabela da tela desenha."""
        linhas = self._rpc("fn_list_company_users", {"p_company_id": self._company_id})
        return rows_to_users(linhas, agora)

    def set_department(self, user_id: str, department: str) -> None:
        self._rpc(
            "fn_set_company_user_department",
            {
                "p_company_id": self._company_id,
                "p_user_id": user_id,
                "p_department": department,
            },
        )

    def _rpc(self, name: str, args: dict):
        """Chama a função e traduz recusa de autorização para o erro de domínio.

        Mesmo motivo do repositório de produtos: a `MainWindow` captura
        `PermissionDeniedError`, e deixar subir a exceção crua do cliente HTTP
        mostraria um traceback onde deveria aparecer a mensagem de permissão.
        """
        try:
            resposta = self._client.rpc(name, args).execute()
        except Exception as erro:
            if _e_recusa_de_permissao(erro):
                raise PermissionDeniedError(
                    ACTION_BY_RPC.get(name, f"executar {name}"), self._role
                ) from erro
            raise
        return getattr(resposta, "data", None) or []


def _mensagem(erro) -> str:
    return getattr(erro, "message", None) or str(erro)


def _e_recusa_de_permissao(erro) -> bool:
    if str(getattr(erro, "code", "")) == PERMISSION_SQLSTATE:
        return True
    texto = _mensagem(erro).casefold()
    return any(trecho in texto for trecho in PERMISSION_HINTS)
