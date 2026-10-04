"""Autenticação pelo Supabase Auth, devolvendo a `Session` do domínio.

Substitui `demo_accounts.autenticar` quando o backend de banco está ligado. A
diferença que importa não é "a senha agora é conferida no servidor": é que o
JWT emitido aqui é o que `fn_current_user_id()` lê para resolver o usuário, e
sem ele TODA função de catálogo recusa por falta de papel.

O login tem três etapas, e nenhuma pode ser pulada:

1. `sign_in_with_password` — prova a identidade e devolve o JWT, que o cliente
   passa a mandar em cada request.
2. `fn_current_user_id()` — traduz o id do Auth para o id de domínio, por
   `user_accounts.auth_user_id`. Devolve NULL quando a conta do Auth não foi
   vinculada; é a falha mais provável numa adoção nova, e por isso ganha
   mensagem própria em vez de virar "sem permissão" três telas adiante.
3. `fn_my_companies()` — empresa e papel. Sem isso não há `company_id` para
   preencher em `fn_create_products` nem papel para a UI aplicar.
"""

from stockflow.domain.entities.session import Session
from stockflow.domain.enums.user_role import UserRole


class AuthenticationError(Exception):
    """Login recusado, ou conta sem vínculo/empresa utilizável."""


CREDENCIAL_INVALIDA = "E-mail ou senha incorretos. Tente novamente."

SEM_VINCULO = (
    "Esta conta existe no Supabase Auth, mas não está vinculada a um usuário "
    "do StockFlow. Um administrador precisa preencher "
    "`user_accounts.auth_user_id` para ela."
)

SEM_EMPRESA = (
    "Esta conta não está ativa em nenhuma empresa. Um administrador precisa "
    "conceder acesso antes do primeiro login."
)


def _dados(resposta):
    return getattr(resposta, "data", None)


def _nome_do_usuario(user, email: str) -> str:
    """Nome de exibição, com o e-mail como último recurso.

    `user_accounts.name` é o LOGIN (minúsculo, sem espaço) e não serve de
    nome próprio na barra lateral; o nome de exibição do Supabase Auth, sim,
    quando preenchido.
    """
    metadata = getattr(user, "user_metadata", None) or {}
    for chave in ("name", "full_name", "display_name"):
        valor = metadata.get(chave)
        if valor:
            return str(valor)
    return email.split("@")[0] if email else "Usuário"


def authenticate(client, email: str, password: str) -> Session:
    """Autentica e monta a sessão. Levanta `AuthenticationError` em qualquer recusa.

    Erro de credencial vira UMA mensagem genérica de propósito: distinguir
    "e-mail não existe" de "senha errada" diz a quem tenta adivinhar quais
    contas existem.
    """
    try:
        resposta = client.auth.sign_in_with_password(
            {"email": (email or "").strip(), "password": password or ""}
        )
    except Exception as erro:
        raise AuthenticationError(CREDENCIAL_INVALIDA) from erro

    user = getattr(resposta, "user", None)
    if user is None:
        raise AuthenticationError(CREDENCIAL_INVALIDA)

    user_id = _dados(client.rpc("fn_current_user_id", {}).execute())
    if not user_id:
        raise AuthenticationError(SEM_VINCULO)

    empresas = _dados(client.rpc("fn_my_companies", {}).execute()) or []
    if not empresas:
        raise AuthenticationError(SEM_EMPRESA)

    # A primeira da lista: `fn_my_companies` já ordena por nome e a tela não
    # tem seletor de empresa. Um usuário em mais de uma empresa entra na
    # primeira — limitação consciente, e o lugar de resolvê-la é a UI, não
    # uma escolha silenciosa aqui.
    empresa = empresas[0]
    email_real = getattr(user, "email", "") or email

    return Session(
        user_id=str(user_id),
        name=_nome_do_usuario(user, email_real),
        email=email_real,
        role=UserRole.from_value(empresa["user_role"]),
        company_id=str(empresa["company_id"]),
    )
