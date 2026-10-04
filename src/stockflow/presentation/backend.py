"""Escolha entre o catálogo de demonstração e o banco.

UM lugar só decide, e as telas não perguntam. `LoginWindow` chama
`authenticate` e a `MainWindow` chama `build_catalog`; nenhuma das duas sabe
se por trás está um dict em memória ou o Supabase.

O PADRÃO É A DEMONSTRAÇÃO, e é opt-in explícito por variável de ambiente, não
"usa banco se houver .env". O `.env` deste repositório já existe para os
scripts de verificação, e deduzir intenção dele faria `uv run stockflow`
mudar de comportamento por causa de um arquivo que ninguém associou à UI —
inclusive falhando o login em máquina sem acesso à rede.

    STOCKFLOW_BACKEND=supabase uv run stockflow
"""

import os

from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.presentation.demo_accounts import autenticar as autenticar_demo
from stockflow.presentation.demo_products import DEMO_PRODUCTS

BACKEND_VAR = "STOCKFLOW_BACKEND"
SUPABASE = "supabase"


def backend_name() -> str:
    return (os.environ.get(BACKEND_VAR) or "demo").strip().casefold()


def using_supabase() -> bool:
    return backend_name() == SUPABASE


def _client():
    from stockflow.infrastructure.database.supabase_client import get_client

    return get_client()


def authenticate(email: str, password: str):
    """Sessão do usuário, ou `None` quando a credencial não confere.

    `None` para credencial inválida mantém o contrato que a `LoginWindow` já
    tratava. Os demais problemas do backend de banco (conta sem vínculo, sem
    empresa, servidor fora) levantam: são condições que o usuário não resolve
    digitando de novo, e devolver `None` as esconderia atrás de "e-mail ou
    senha incorretos".
    """
    if not using_supabase():
        return autenticar_demo(email, password)

    from stockflow.infrastructure.auth.supabase_auth import (
        CREDENCIAL_INVALIDA,
        AuthenticationError,
        authenticate as autenticar_supabase,
    )

    try:
        return autenticar_supabase(_client(), email, password)
    except AuthenticationError as erro:
        if str(erro) == CREDENCIAL_INVALIDA:
            return None
        raise


def build_catalog(session):
    """Devolve `(catalogo, repositorio)` para a janela montar as telas.

    Os dois juntos porque precisam compartilhar o MESMO dict: é a identidade
    entre o que o repositório grava e o que as telas leem que faz uma
    gravação aparecer na tabela sem recarregar a aplicação inteira.

    No modo banco o dict é uma FOTO do catálogo no login. Ele continua sendo
    a fonte das telas, e cada gravação atualiza banco e foto — o que esta
    versão não tem é atualização vinda de outro usuário sem recarregar.
    """
    if not using_supabase():
        catalogo = dict(DEMO_PRODUCTS)
        return catalogo, DemoProductRepository(catalogo)

    from stockflow.infrastructure.repositories.supabase_product_repository import (
        SupabaseProductRepository,
    )

    company_id = getattr(session, "company_id", None)
    if not company_id:
        raise RuntimeError(
            "A sessão não tem empresa. Com STOCKFLOW_BACKEND=supabase o login "
            "precisa resolver a empresa do usuário antes de abrir o catálogo."
        )

    repositorio = SupabaseProductRepository(
        _client(), company_id, role=getattr(session, "role", None)
    )
    return repositorio.load_catalog(), repositorio


def build_movement_repository(session, catalogo):
    """Repositório de movimentações, no mesmo par demonstração/banco.

    Recebe o catálogo porque o adaptador de demonstração precisa dele: sem
    banco não há trigger, então confirmar uma movimentação tem que recalcular
    o saldo do produto no dict que as telas leem. O adaptador de banco ignora
    o argumento — lá quem recalcula é o trigger.
    """
    if not using_supabase():
        from stockflow.infrastructure.repositories.demo_movement_repository import (
            DemoMovementRepository,
        )

        return DemoMovementRepository(catalogo)

    from stockflow.infrastructure.repositories.supabase_movement_repository import (
        SupabaseMovementRepository,
    )

    company_id = getattr(session, "company_id", None)
    if not company_id:
        raise RuntimeError(
            "A sessão não tem empresa. `fn_register_movement` precisa do "
            "company_id para registrar a movimentação."
        )

    return SupabaseMovementRepository(
        _client(), company_id, role=getattr(session, "role", None)
    )


def build_user_directory(session):
    """Linhas da tela de Usuários, ou `None` para manter a demonstração.

    `None` em vez de devolver as linhas da demonstração: quem chama precisa
    distinguir "não há banco configurado" de "o banco respondeu uma lista
    vazia". No primeiro caso a tela fica como está; no segundo ela precisa
    mostrar que a empresa realmente não tem usuário nenhum.
    """
    if not using_supabase():
        return None

    from stockflow.infrastructure.repositories.supabase_user_repository import (
        SupabaseUserRepository,
    )

    company_id = getattr(session, "company_id", None)
    if not company_id:
        raise RuntimeError(
            "A sessão não tem empresa. `fn_list_company_users` precisa do "
            "company_id para listar os usuários."
        )

    return SupabaseUserRepository(
        _client(), company_id, role=getattr(session, "role", None)
    ).list_users()
