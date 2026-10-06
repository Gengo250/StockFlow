"""US05 — autenticar usuarios e gerenciar sessoes.

Dois cartoes, pelos criterios de aceite:

1. Entrada por login e senha, consultando a conta e verificando status.
   Sessao so depois de autenticacao valida. Conta ativa com credencial
   correta entra; conta inativa ou credencial incorreta tem acesso negado.
2. Contexto de sessao criado no login e encerrado no logout. Depois de
   autenticar o sistema identifica a conta; depois do logout, uma nova
   operacao protegida exige autenticacao.

Os testes entram pela `LoginWindow` e pelo `LoginFlow` reais, nao pelas
funcoes de backend: o criterio fala do sistema, e e na fiacao entre janela,
fluxo e backend que a sessao ja vazou antes.
"""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.permissions import ensure_can_manage_users
from stockflow.presentation import backend
from stockflow.presentation.app import LoginFlow
from stockflow.presentation.demo_accounts import alterar_status_demo, conta_por_papel
from stockflow.presentation.demo_status import reset_demo_user_statuses


@pytest.fixture(autouse=True)
def demonstracao(monkeypatch):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    reset_demo_user_statuses()
    # Os QMessageBox do fluxo sao modais: sem isto o `exec()` trava a suite.
    # Ficam registrados para o teste poder cobrar que a recusa foi explicada.
    avisos = []
    for metodo in ("critical", "warning", "information"):
        monkeypatch.setattr(
            QMessageBox, metodo,
            staticmethod(lambda *a, **k: avisos.append(a)),
        )
    yield avisos
    reset_demo_user_statuses()


@pytest.fixture
def configuracao(tmp_path):
    return QSettings(str(tmp_path / "us05.ini"), QSettings.IniFormat)


@pytest.fixture
def fluxo(qapp, configuracao):
    flow = LoginFlow(configuracao)
    yield flow
    if flow.main is not None:
        flow.main.close()
    flow.login.close()


def credenciais(papel=UserRole.ADMIN):
    conta = conta_por_papel(papel)
    return conta.email, conta.password


def entrar(flow, email, senha):
    flow.login.email_input.setText(email)
    flow.login.password_input.setText(senha)
    flow.login.submit_button.click()


# ------------------------------------------------ cartao 1: autenticacao


def test_conta_ativa_com_credencial_correta_entra(fluxo):
    email, senha = credenciais()

    entrar(fluxo, email, senha)

    assert fluxo.main is not None, "login valido nao abriu o sistema"
    assert fluxo.main.session.email == email


def test_credencial_incorreta_tem_acesso_negado(fluxo):
    email, _ = credenciais()

    entrar(fluxo, email, "senha-errada")

    assert fluxo.main is None, "senha errada criou sessao"
    assert fluxo.login.error.text(), "a recusa precisa ser explicada na tela"


def test_email_inexistente_tem_acesso_negado(fluxo):
    entrar(fluxo, "ninguem@stockflow.com.br", "qualquer")

    assert fluxo.main is None


def test_conta_inativa_tem_acesso_negado(fluxo):
    """Status da conta e consultado no login, nao so na hora de operar.

    A conta inativada aqui e a de ESTOQUE, nao a de admin: a demonstracao
    recusa inativar o ultimo administrador, pela mesma regra que o gatilho
    `trg_company_users_keep_admin` aplica no banco.
    """
    conta = conta_por_papel(UserRole.STOCK)
    alterar_status_demo(conta.user_id, False)

    entrar(fluxo, conta.email, conta.password)

    assert fluxo.main is None, "conta inativa entrou no sistema"
    assert fluxo.login.error.text(), "a recusa precisa ser explicada na tela"


def test_a_mesma_conta_entra_depois_de_reativada(fluxo):
    """Guarda do oposto: a recusa e pelo STATUS, nao pela conta em si."""
    conta = conta_por_papel(UserRole.STOCK)
    alterar_status_demo(conta.user_id, False)
    alterar_status_demo(conta.user_id, True)

    entrar(fluxo, conta.email, conta.password)

    assert fluxo.main is not None
    assert fluxo.main.session.email == conta.email


def test_senha_vazia_nao_entra(fluxo):
    email, _ = credenciais()

    entrar(fluxo, email, "")

    assert fluxo.main is None


# ------------------------------------------------- cartao 2: contexto de sessao


def test_apos_autenticar_o_sistema_identifica_a_conta(fluxo):
    email, senha = credenciais()

    entrar(fluxo, email, senha)

    sessao = fluxo.main.session
    assert sessao.user_id and sessao.role is UserRole.ADMIN
    # A identificacao precisa estar VISIVEL, nao so no objeto.
    assert sessao.name in fluxo.main.sidebar.user_name.text()


def test_a_sessao_carrega_o_papel_que_libera_as_areas_protegidas(fluxo):
    email, senha = credenciais(UserRole.SELLER)

    entrar(fluxo, email, senha)

    assert fluxo.main.session.role is UserRole.SELLER
    assert fluxo.main.show_page("usuarios") is False


def test_logout_encerra_o_contexto_e_devolve_a_tela_de_login(fluxo):
    email, senha = credenciais()
    entrar(fluxo, email, senha)

    fluxo.logout()

    assert fluxo.main is None, "o contexto da sessao sobreviveu ao logout"
    assert fluxo.login.isVisible()
    assert fluxo.login.password_input.text() == "", "a senha ficou no formulario"


def test_apos_logout_operacao_protegida_exige_autenticacao(fluxo):
    """Criterio do cartao: operacao protegida depois do logout pede login.

    Sem sessao, a politica nega — e e a mesma politica que o banco espelha
    em `fn_is_admin`.
    """
    email, senha = credenciais()
    entrar(fluxo, email, senha)
    fluxo.logout()

    with pytest.raises(PermissionDeniedError):
        ensure_can_manage_users(None)


def test_logout_encerra_a_sessao_no_backend(fluxo, monkeypatch):
    saidas = []
    monkeypatch.setattr(backend, "sign_out", lambda: saidas.append(True))
    email, senha = credenciais()
    entrar(fluxo, email, senha)

    fluxo.logout()

    assert saidas == [True], "o logout nao encerrou a sessao no backend"


def test_entrar_de_novo_depois_do_logout_monta_contexto_novo(fluxo):
    """Relogin nao pode reaproveitar o contexto de quem saiu."""
    admin_email, admin_senha = credenciais(UserRole.ADMIN)
    entrar(fluxo, admin_email, admin_senha)
    primeira = fluxo.main
    fluxo.logout()

    vendedor_email, vendedor_senha = credenciais(UserRole.SELLER)
    entrar(fluxo, vendedor_email, vendedor_senha)

    assert fluxo.main is not primeira, "a janela do usuario anterior foi reaproveitada"
    assert fluxo.main.session.email == vendedor_email
    assert fluxo.main.session.role is UserRole.SELLER
