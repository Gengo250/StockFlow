"""Administração de usuários restrita ao ADMIN, na janela principal.

O banco já decide isso em `database/code/procedures/03_users.sql`: criar,
editar, ativar/desativar e até LISTAR usuário exigem `fn_is_admin`. Então a
tela inteira é privilégio de ADMIN — o item sai do menu para os demais.

Como na US01, o critério de aceite não é "o botão some": é que o papel sem
permissão não chegue à tela nem quando o controle visual é burlado. Por isso
os testes mais importantes aqui chamam `show_page("usuarios")` direto,
ignorando o menu.
"""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.app import LoginFlow
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.widgets.sidebar import DEFAULT_KEY
from stockflow.presentation.widgets.user_table import DEMO_USERS
from stockflow.presentation.windows.login_window import DEMO_EMAIL, DEMO_PASSWORD
from stockflow.presentation.windows.main_window import MainWindow

SEM_PERMISSAO = [UserRole.STOCK, UserRole.SELLER]


def sessao(papel):
    return conta_por_papel(papel).session()


@pytest.fixture
def sem_dialogos(monkeypatch):
    """Silencia os QMessageBox modais, que travariam o teste no `exec()`."""
    chamadas = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda *args, **kwargs: chamadas.append(args)),
    )
    return chamadas


@pytest.fixture
def janela(qapp, request):
    """Fábrica de MainWindow já visível, fechada no fim do teste."""
    abertas = []

    def criar(sessao_do_teste=None):
        window = MainWindow(sessao_do_teste)
        abertas.append(window)
        window.show()
        return window

    request.addfinalizer(lambda: [w.close() for w in abertas])
    return criar


# ------------------------------------------------------------- ADMIN


def test_admin_ve_o_item_de_usuarios_no_menu(janela):
    window = janela(sessao(UserRole.ADMIN))

    assert not window.sidebar.buttons["usuarios"].isHidden()
    assert window.sidebar.buttons["usuarios"].isVisible()


def test_admin_recebe_os_controles_de_usuario_habilitados(janela):
    window = janela(sessao(UserRole.ADMIN))
    page = window.users_page

    assert page.new_user_button.isEnabled()
    assert page.user_table.edit_buttons
    assert all(b.isEnabled() for b in page.user_table.edit_buttons)


def test_admin_navega_para_a_tela_de_usuarios(janela, sem_dialogos):
    window = janela(sessao(UserRole.ADMIN))

    assert window.show_page("usuarios") is True
    assert window.pages.currentWidget() is window.users_page
    assert window.last_navigation_error is None
    assert sem_dialogos == []


# -------------------------------------------- papéis sem permissão


@pytest.mark.parametrize("papel", SEM_PERMISSAO)
def test_papel_sem_permissao_nao_ve_o_item_de_usuarios_no_menu(janela, papel):
    window = janela(sessao(papel))

    assert window.sidebar.buttons["usuarios"].isHidden()
    # O resto do menu continua inteiro: a restrição é da tela de usuários.
    assert not window.sidebar.buttons["estoque"].isHidden()
    assert not window.sidebar.buttons["configuracoes"].isHidden()


@pytest.mark.parametrize("papel", SEM_PERMISSAO)
def test_papel_sem_permissao_recebe_os_controles_de_usuario_desabilitados(
    janela, papel
):
    """Defesa em profundidade: mesmo sem alcançar a tela, ela nasce travada."""
    window = janela(sessao(papel))
    page = window.users_page

    assert not page.new_user_button.isEnabled()
    assert page.user_table.edit_buttons
    assert not any(b.isEnabled() for b in page.user_table.edit_buttons)


@pytest.mark.parametrize("papel", SEM_PERMISSAO)
def test_papel_sem_permissao_nao_abre_a_tela_nem_por_show_page(
    janela, sem_dialogos, papel
):
    """Critério de aceite: a recusa não vive no botão escondido."""
    window = janela(sessao(papel))
    pagina_anterior = window.pages.currentWidget()

    assert window.show_page("usuarios") is False

    assert window.pages.currentWidget() is pagina_anterior
    assert window.pages.currentWidget() is not window.users_page
    assert isinstance(window.last_navigation_error, PermissionError)
    assert window.last_navigation_error.role == papel
    assert sem_dialogos, "o usuário precisa ver o motivo da recusa"


@pytest.mark.parametrize("papel", SEM_PERMISSAO)
def test_recusa_de_navegacao_nao_marca_o_item_como_ativo(
    janela, sem_dialogos, papel
):
    """Janela em estado coerente: nada de menu apontando para tela fechada."""
    window = janela(sessao(papel))

    window.show_page("usuarios")

    assert window.sidebar.buttons["usuarios"].objectName() != "activeButton"
    assert window.sidebar.buttons[DEFAULT_KEY].objectName() == "activeButton"


@pytest.mark.parametrize("papel", SEM_PERMISSAO)
def test_papel_sem_permissao_nao_abre_o_formulario_de_usuario(janela, papel):
    """Caminho residual: o duplo clique na linha não passa pelos botões."""
    window = janela(sessao(papel))
    page = window.users_page
    linha = DEMO_USERS[0]

    # Se o formulário abrisse, `exec()` bloquearia o teste aqui.
    assert page._open_form(linha) is None


def test_janela_sem_sessao_nao_gerencia_usuarios(janela, sem_dialogos):
    """Sem login não há papel: a tela de usuários fica fechada."""
    window = janela()

    assert window.sidebar.buttons["usuarios"].isHidden()
    assert not window.users_page.new_user_button.isEnabled()
    assert window.show_page("usuarios") is False


# ------------------------------------------------------------ relogin


def test_relogar_como_vendedor_esconde_o_item_de_usuarios(qapp, tmp_path, sem_dialogos):
    """O furo da US01, agora no menu: a janela do ADMIN sobrevive ao logout."""
    settings = QSettings(f"{tmp_path}/relogin-usuarios.ini", QSettings.IniFormat)
    flow = LoginFlow(settings)
    try:
        flow.login.email_input.setText(DEMO_EMAIL)
        flow.login.password_input.setText(DEMO_PASSWORD)
        flow.login.submit_button.click()
        assert flow.main.session.role == UserRole.ADMIN
        assert not flow.main.sidebar.buttons["usuarios"].isHidden()
        flow.main.show_page("usuarios")
        assert flow.main.pages.currentWidget() is flow.main.users_page

        flow.main.sidebar.logout_button.click()

        vendedor = conta_por_papel(UserRole.SELLER)
        flow.login.email_input.setText(vendedor.email)
        flow.login.password_input.setText(vendedor.password)
        flow.login.submit_button.click()

        assert flow.main.session.role == UserRole.SELLER
        assert flow.main.sidebar.buttons["usuarios"].isHidden()
        assert not flow.main.users_page.new_user_button.isEnabled()
        # A tela que o ADMIN deixou aberta não pode continuar na frente.
        assert flow.main.pages.currentWidget() is not flow.main.users_page
    finally:
        if flow.main is not None:
            flow.main.close()
        flow.login.close()


def test_relogar_como_admin_devolve_o_item_de_usuarios(qapp, tmp_path):
    """A recíproca: esconder não pode ser caminho só de ida."""
    settings = QSettings(f"{tmp_path}/relogin-admin.ini", QSettings.IniFormat)
    flow = LoginFlow(settings)
    try:
        vendedor = conta_por_papel(UserRole.SELLER)
        flow.login.email_input.setText(vendedor.email)
        flow.login.password_input.setText(vendedor.password)
        flow.login.submit_button.click()
        assert flow.main.sidebar.buttons["usuarios"].isHidden()

        flow.main.sidebar.logout_button.click()

        flow.login.email_input.setText(DEMO_EMAIL)
        flow.login.password_input.setText(DEMO_PASSWORD)
        flow.login.submit_button.click()

        assert flow.main.session.role == UserRole.ADMIN
        assert not flow.main.sidebar.buttons["usuarios"].isHidden()
        assert flow.main.users_page.new_user_button.isEnabled()
        assert all(
            b.isEnabled() for b in flow.main.users_page.user_table.edit_buttons
        )
        assert flow.main.show_page("usuarios") is True
    finally:
        if flow.main is not None:
            flow.main.close()
        flow.login.close()
