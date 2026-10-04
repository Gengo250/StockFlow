"""Escolha do backend por `STOCKFLOW_BACKEND`.

O risco que estes testes fecham é o do padrão errado: se a aplicação
resolvesse usar o banco só por existir um `.env` no repositório — e ele
existe, para os scripts de verificação — `uv run stockflow` passaria a exigir
rede e credencial válida para mostrar a tela de login, numa máquina onde
nada disso foi pedido.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation import backend
from stockflow.presentation.demo_accounts import (
    DEMO_ACCOUNTS,
    conta_admin,
)
from stockflow.presentation.demo_status import reset_demo_user_statuses


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    monkeypatch.delenv(backend.BACKEND_VAR, raising=False)
    reset_demo_user_statuses()
    yield
    reset_demo_user_statuses()


def test_o_padrao_e_a_demonstracao():
    assert backend.backend_name() == "demo"
    assert backend.using_supabase() is False


def test_env_vazio_ou_desconhecido_continua_em_demonstracao(monkeypatch):
    for valor in ("", "   ", "postgres", "sqlite"):
        monkeypatch.setenv(backend.BACKEND_VAR, valor)
        assert backend.using_supabase() is False, valor


def test_opt_in_e_explicito_e_ignora_caixa(monkeypatch):
    for valor in ("supabase", "SUPABASE", " Supabase "):
        monkeypatch.setenv(backend.BACKEND_VAR, valor)
        assert backend.using_supabase() is True, valor


def test_demonstracao_autentica_pelas_contas_locais():
    conta = conta_admin()
    sessao = backend.authenticate(conta.email, conta.password)
    assert sessao is not None and sessao.role is UserRole.ADMIN
    assert backend.authenticate(conta.email, "errada") is None


def test_desativar_e_reativar_conta_demo_bloqueia_e_libera_login():
    admin = conta_admin()
    alvo = next(account for account in DEMO_ACCOUNTS if account.role is UserRole.STOCK)

    backend.set_user_active(admin.session(), alvo.user_id, False)
    assert backend.authenticate(alvo.email, alvo.password) is None
    assert "Inativo" in next(
        row[4] for row in backend.build_demo_user_directory()
        if row.user_id == alvo.user_id
    )

    backend.set_user_active(admin.session(), alvo.user_id, True)
    assert backend.authenticate(alvo.email, alvo.password).user_id == alvo.user_id
    assert "Ativo" in next(
        row[4] for row in backend.build_demo_user_directory()
        if row.user_id == alvo.user_id
    )


def test_demo_impede_desativar_o_unico_admin():
    admin = conta_admin()

    with pytest.raises(ValueError, match="ao menos um administrador"):
        backend.set_user_active(admin.session(), admin.user_id, False)

    assert backend.authenticate(admin.email, admin.password) is not None


def test_status_demo_volta_ao_padrao_quando_a_memoria_e_reiniciada():
    admin = conta_admin()
    alvo = next(account for account in DEMO_ACCOUNTS if account.role is UserRole.STOCK)
    backend.set_user_active(admin.session(), alvo.user_id, False)
    assert backend.authenticate(alvo.email, alvo.password) is None

    reset_demo_user_statuses()

    assert backend.authenticate(alvo.email, alvo.password) is not None


def test_demonstracao_entrega_catalogo_e_repositorio_ligados():
    """A identidade entre dict e repositório é o que faz a tela refletir."""
    catalogo, repositorio = backend.build_catalog(conta_admin().session())

    assert catalogo, "catálogo de demonstração veio vazio"
    assert repositorio.exists(next(iter(catalogo))) is True

    # O repositório grava NO MESMO dict que as telas leem.
    assert repositorio.list_all() == tuple(catalogo.values())


def test_cada_janela_recebe_a_sua_copia_do_catalogo_de_demonstracao():
    """Duas janelas não podem dividir o dict do módulo.

    Com o catálogo compartilhado, desativar um produto numa janela mudaria a
    outra — e, pior, sobreviveria ao fechamento das duas.
    """
    primeiro, _ = backend.build_catalog(conta_admin().session())
    segundo, _ = backend.build_catalog(conta_admin().session())
    assert primeiro is not segundo
    assert primeiro == segundo


def test_supabase_sem_empresa_na_sessao_falha_alto(monkeypatch):
    """Sessão sem `company_id` não pode virar catálogo vazio em silêncio.

    `fn_create_products` exige `p_company_id`; sem empresa, a tela abriria
    sem produto nenhum e todo cadastro seria recusado pelo banco sem que a
    causa aparecesse em lugar nenhum.
    """
    monkeypatch.setenv(backend.BACKEND_VAR, "supabase")
    sessao = conta_admin().session()          # demo: nasce sem company_id
    assert sessao.company_id is None

    with pytest.raises(RuntimeError, match="empresa"):
        backend.build_catalog(sessao)
