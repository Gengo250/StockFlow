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

from stockflow.infrastructure.repositories.demo_client_repository import (
    DemoClientRepository,
)
from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.presentation.demo_accounts import (
    alterar_status_demo,
    autenticar as autenticar_demo,
)
from stockflow.presentation.demo_data import base_de_clientes
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


def build_movement_repository(session, catalogo, supplier_repository=None):
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

        return DemoMovementRepository(catalogo, suppliers=supplier_repository)

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


def build_supplier_repository(session=None):
    """Fornecedor em demonstração ou no banco, compartilhado pela janela."""
    if not using_supabase():
        from stockflow.infrastructure.repositories.demo_supplier_repository import (
            DemoSupplierRepository,
        )

        return DemoSupplierRepository()

    from stockflow.infrastructure.repositories.supabase_supplier_repository import (
        SupabaseSupplierRepository,
    )

    company_id = getattr(session, "company_id", None)
    if not company_id:
        raise RuntimeError(
            "A sessão não tem empresa. As funções de fornecedor exigem company_id."
        )
    return SupabaseSupplierRepository(
        _client(), company_id, role=getattr(session, "role", None)
    )


def build_demo_user_directory():
    """Linhas demo atualizadas durante esta execução do aplicativo."""
    from stockflow.presentation.demo_data import linhas_de_usuarios

    rows = {row.user_id: row for row in linhas_de_usuarios()}
    rows.update(_demo_users)
    return tuple(rows.values())


def build_client_repository(session=None):
    if not using_supabase():
        return DemoClientRepository()
    from stockflow.infrastructure.repositories.supabase_client_repository import SupabaseClientRepository
    if not getattr(session, "company_id", None):
        raise RuntimeError("A sessão não tem empresa.")
    return SupabaseClientRepository(_client(), session.company_id, role=session.role)


def build_sale_repository(session, products):
    if not using_supabase():
        from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
        return DemoSaleRepository()
    from stockflow.infrastructure.repositories.supabase_sale_repository import SupabaseSaleRepository
    return SupabaseSaleRepository(_client(), session.company_id)


def build_client_directory(session=None):
    return build_client_repository(session).list_all()


def set_client_active(session, client_id, active):
    from stockflow.application.services.client_service import ClientService
    return ClientService(build_client_repository(session), session).set_active(client_id, active)


def sign_out():
    if using_supabase():
        from stockflow.infrastructure.database.supabase_client import reset_client
        try:
            _client().auth.sign_out()
        finally:
            reset_client()


def set_user_active(session, user_id: str, active: bool) -> None:
    """Ativa/desativa o vínculo da empresa atual ou a conta demo em memória."""
    from stockflow.domain.permissions import ensure_can_manage_users

    ensure_can_manage_users(session, action="alterar o status de usuários")
    if not user_id:
        raise ValueError("Não foi possível identificar o usuário selecionado.")

    if not using_supabase():
        alterar_status_demo(user_id, active)
        return

    company_id = getattr(session, "company_id", None)
    if not company_id:
        raise RuntimeError(
            "A sessão não tem empresa. `fn_toggle_company_user` precisa do "
            "company_id para alterar o status."
        )

    from stockflow.infrastructure.repositories.supabase_user_repository import (
        SupabaseUserRepository,
    )

    SupabaseUserRepository(
        _client(), company_id, role=getattr(session, "role", None)
    ).set_active(user_id, active)


_demo_users = {}


def independent_auth_client():
    from stockflow.infrastructure.database.supabase_client import _credenciais
    from supabase import create_client, ClientOptions
    url, key = _credenciais()
    return create_client(url, key, options=ClientOptions(persist_session=False, auto_refresh_token=False))


def save_user(session, *, user_id=None, name, email, role, department="", password=""):
    import re
    from stockflow.domain.permissions import ensure_can_manage_users
    from stockflow.domain.enums.user_role import UserRole
    ensure_can_manage_users(session)
    role = UserRole.from_value(role)
    name, email = name.strip(), email.strip().lower()
    if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Informe nome e e-mail válidos.")
    if not using_supabase():
        from uuid import uuid4
        from stockflow.presentation.user_directory_row import UserDirectoryRow
        from stockflow.presentation.roles import rotulo_de_papel
        from stockflow.presentation.demo_accounts import DemoAccount, DEMO_ACCOUNTS_BY_EMAIL
        existing = next((r for r in build_demo_user_directory() if r.user_id == user_id), None)
        if not user_id and (email in DEMO_ACCOUNTS_BY_EMAIL or any(r[1] == email for r in build_demo_user_directory())):
            raise ValueError("E-mail já cadastrado.")
        if not user_id and len(password) < 6:
            raise ValueError("Defina uma senha inicial de pelo menos 6 caracteres.")
        user_id = user_id or f"USR-{uuid4().hex[:8]}"
        _demo_users[user_id] = UserDirectoryRow((name, email, department or "—", rotulo_de_papel(role),
                                               existing[4] if existing else "Ativo", existing[5] if existing else "Nunca", "#2563EB"), user_id=user_id)
        account = next((a for a in DEMO_ACCOUNTS_BY_EMAIL.values() if a.user_id == user_id), None)
        if account or password:
            if account:
                DEMO_ACCOUNTS_BY_EMAIL.pop(account.email, None)
            DEMO_ACCOUNTS_BY_EMAIL[email] = DemoAccount(user_id, name, email, password or account.password, role)
        return user_id
    args = {"p_company_id": session.company_id, "p_user_id": user_id,
            "p_email": email, "p_name": name, "p_role": role.value, "p_department": department}
    try:
        return _client().rpc("fn_save_company_member", args).execute().data
    except Exception as error:
        if user_id or str(getattr(error, "code", "")) != "P0002":
            raise
    if len(password) < 6:
        raise ValueError("Conta ainda não existe. Defina uma senha inicial de pelo menos 6 caracteres.")
    # A separate Auth client prevents signup from replacing the administrator's session.
    auth_client = independent_auth_client()
    try:
        auth_client.auth.sign_up({"email": email, "password": password})
        try:
            return _client().rpc("fn_save_company_member", args).execute().data
        except Exception as error:
            raise RuntimeError("Conta de acesso criada, mas o vínculo não foi concluído. Repita o cadastro com o mesmo e-mail para vincular a conta.") from error
    finally:
        try:
            auth_client.auth.sign_out()
        except Exception:
            pass
