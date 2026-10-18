"""H14 — perfis e permissões conferidos pelo caminho do usuário.

Um teste por critério de aceite da história:

1. o administrador atribui perfil;
2. áreas e ações respeitam a permissão configurada, para os três papéis;
3. quem não tem permissão recebe recusa SEM alteração de dados;
4. a operação registra o usuário autenticado.

Os testes de menu e navegação varrem a matriz inteira em vez de citar três
telas na mão: área nova entra na varredura sozinha, que é o ponto de ter uma
matriz. O critério não é "o botão some" — é que o papel sem permissão não
chegue à tela nem quando o controle visual é burlado, por isso as chamadas a
`show_page` ignoram o menu de propósito.
"""

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.permissions import PERMISSION_MATRIX, pode_ver
from stockflow.presentation import backend
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.roles import rotulo_de_papel
from stockflow.presentation.widgets.sidebar import MENU_ITEMS, SYSTEM_ITEMS
from stockflow.presentation.windows.main_window import MainWindow

PAPEIS = [UserRole.ADMIN, UserRole.STOCK, UserRole.SELLER]
SEM_PERMISSAO = [UserRole.STOCK, UserRole.SELLER]

#: Só as áreas que existem como item de menu: a matriz também descreve telas
#: alcançadas por outros caminhos, e `show_page` só aceita as do menu.
AREAS_DE_MENU = sorted(
    {chave for chave, _, _ in MENU_ITEMS + SYSTEM_ITEMS} & set(PERMISSION_MATRIX)
)


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
def diretorio_isolado(monkeypatch):
    """Isola as alterações de usuário feitas no backend de demonstração.

    São DOIS estados de módulo, e esquecer o segundo custou uma falha remota:
    `backend._demo_users` guarda as linhas do diretório, mas `save_user`
    também reescreve `DEMO_ACCOUNTS_BY_EMAIL`, que é a base de LOGIN. Sem
    copiar a segunda, trocar o perfil de uma conta aqui mudava o papel com que
    ela entra no sistema — e um teste de login noutro arquivo passava a ver
    um vendedor onde esperava um estoquista.
    """
    from stockflow.presentation import demo_accounts

    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setattr(backend, "_demo_users", {})
    monkeypatch.setattr(
        demo_accounts,
        "DEMO_ACCOUNTS_BY_EMAIL",
        dict(demo_accounts.DEMO_ACCOUNTS_BY_EMAIL),
    )
    return backend.build_demo_user_directory


def papel_exibido(diretorio, user_id):
    """Perfil que a tela mostra para um usuário, pelo contrato de demo_data."""
    for linha in diretorio():
        if linha.user_id == user_id:
            return linha[3]
    raise LookupError(user_id)


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


# ------------------------------------------------ critério 2: áreas e ações


@pytest.mark.parametrize("papel", PAPEIS)
@pytest.mark.parametrize("area", AREAS_DE_MENU)
def test_o_menu_mostra_exatamente_o_que_a_matriz_permite(janela, area, papel):
    """Item visível se, e somente se, o papel pode abrir a área."""
    window = janela(sessao(papel))
    botao = window.sidebar.buttons[area]

    assert botao.isVisible() is pode_ver(papel, area), (
        f"{papel.value} em '{area}': menu mostra {botao.isVisible()}, "
        f"matriz diz {pode_ver(papel, area)}"
    )


@pytest.mark.parametrize("papel", PAPEIS)
@pytest.mark.parametrize("area", AREAS_DE_MENU)
def test_a_navegacao_recusa_a_area_que_a_matriz_nega(
    janela, sem_dialogos, area, papel
):
    """Burlar o menu e chamar `show_page` direto não abre a tela.

    Esconder o item é controle visual, e controle visual se burla: a
    verificação precisa morar no método que de fato troca a tela.
    """
    window = janela(sessao(papel))

    assert window.show_page(area) is pode_ver(papel, area)


@pytest.mark.parametrize("papel", PAPEIS)
def test_a_recusa_nomeia_a_area_que_foi_negada(janela, sem_dialogos, papel):
    """A mensagem fala da tela recusada, não de outra qualquer.

    O ternário anterior só distinguia fornecedores: o vendedor barrado em
    Movimentações era informado de que não podia "abrir a administração de
    usuários" — uma tela que ele nem tinha pedido.
    """
    window = janela(sessao(papel))

    for area in AREAS_DE_MENU:
        if pode_ver(papel, area):
            continue
        window.show_page(area)
        erro = window.last_navigation_error

        rotulo = dict(
            (chave, nome) for chave, nome, _ in MENU_ITEMS + SYSTEM_ITEMS
        )[area]
        assert rotulo.lower() in str(erro).lower(), (
            f"recusa em '{area}' não cita '{rotulo}': {erro}"
        )


@pytest.mark.parametrize("papel", PAPEIS)
def test_a_pagina_aberta_e_abandonada_quando_a_permissao_some(janela, sem_dialogos, papel):
    """Relogin não pode deixar o próximo usuário olhando a tela do anterior."""
    admin = janela(sessao(UserRole.ADMIN))
    restritas = [a for a in AREAS_DE_MENU if not pode_ver(papel, a)]
    if not restritas:
        pytest.skip(f"{papel.value} alcança todas as áreas de menu")

    assert admin.show_page(restritas[0]) is True
    admin.apply_session(sessao(papel))

    assert admin.pages.currentWidget() is not admin.page_widgets[restritas[0]]


# --------------------------------------- critério 1: o admin atribui perfil


def test_admin_atribui_perfil_e_a_troca_aparece_no_diretorio(diretorio_isolado):
    """O administrador troca o perfil de um usuário e a troca persiste."""
    alvo = conta_por_papel(UserRole.STOCK)
    assert papel_exibido(diretorio_isolado, alvo.user_id) == rotulo_de_papel(UserRole.STOCK)

    backend.save_user(
        sessao(UserRole.ADMIN),
        user_id=alvo.user_id,
        name=alvo.name,
        email=alvo.email,
        role=UserRole.SELLER,
        department="Vendas",
    )

    assert papel_exibido(diretorio_isolado, alvo.user_id) == rotulo_de_papel(UserRole.SELLER)


def test_o_formulario_oferece_os_tres_perfis(qapp):
    """Atribuir perfil exige poder escolher entre eles."""
    from stockflow.presentation.widgets.user_form import UserForm

    form = UserForm(pode_gerenciar=True)
    try:
        oferecidos = {form.role_input.itemData(i) for i in range(form.role_input.count())}
        assert oferecidos == {papel.value for papel in PAPEIS}
    finally:
        form.deleteLater()


def test_formulario_envia_perfil_selecionado_ao_rpc_do_supabase(qapp, monkeypatch):
    """O caminho persistente grava no vínculo da empresa, não só na demo."""
    from types import SimpleNamespace

    from stockflow.presentation.user_directory_row import UserDirectoryRow
    from stockflow.presentation.widgets.user_form import UserForm

    target_id = "44444444-4444-4444-4444-444444444444"
    company_id = "11111111-1111-1111-1111-111111111111"

    class ClienteRPC:
        def __init__(self):
            self.chamadas = []

        def rpc(self, nome, argumentos):
            self.chamadas.append((nome, argumentos))

            class Chamada:
                def execute(self):
                    return SimpleNamespace(data=target_id)

            return Chamada()

    cliente = ClienteRPC()
    monkeypatch.setenv("STOCKFLOW_BACKEND", "supabase")
    monkeypatch.setattr(backend, "_client", lambda: cliente)
    admin = SimpleNamespace(role=UserRole.ADMIN, company_id=company_id)
    usuario = UserDirectoryRow(
        ("Carlos Mendes", "carlos@example.com", "Estoque", "Estoque",
         "Ativo", "Nunca", "#195BFF"),
        user_id=target_id,
    )
    form = UserForm(
        usuario,
        pode_gerenciar=True,
        on_save=lambda **dados: backend.save_user(admin, **dados),
    )
    try:
        form.role_input.setCurrentIndex(form.role_input.findData(UserRole.SELLER.value))
        form._save()

        assert cliente.chamadas == [(
            "fn_save_company_member",
            {
                "p_company_id": company_id,
                "p_user_id": target_id,
                "p_email": "carlos@example.com",
                "p_name": "Carlos Mendes",
                "p_role": UserRole.SELLER.value,
                "p_department": "Estoque",
            },
        )]
        assert form.result() == QDialog.DialogCode.Accepted
    finally:
        form.deleteLater()


# ------------------------- critério 3: recusa sem alteração de dados


@pytest.mark.parametrize("papel", SEM_PERMISSAO)
def test_papel_sem_permissao_nao_atribui_perfil_nem_altera_dados(diretorio_isolado, papel):
    """A recusa acontece ANTES de qualquer gravação.

    Não basta levantar a exceção: o diretório precisa continuar exatamente
    como estava. Uma guarda que nega depois de gravar já perdeu.
    """
    alvo = conta_por_papel(UserRole.STOCK)
    antes = tuple(diretorio_isolado())

    with pytest.raises(PermissionDeniedError):
        backend.save_user(
            sessao(papel),
            user_id=alvo.user_id,
            name=alvo.name,
            email=alvo.email,
            role=UserRole.ADMIN,
        )

    assert tuple(diretorio_isolado()) == antes
    assert papel_exibido(diretorio_isolado, alvo.user_id) == rotulo_de_papel(UserRole.STOCK)


def test_sessao_ausente_nao_atribui_perfil(diretorio_isolado):
    """Falha fechada: sem sessão, nega — o caminho de um usuário não logado."""
    antes = tuple(diretorio_isolado())

    with pytest.raises(PermissionDeniedError):
        backend.save_user(None, name="Intruso", email="intruso@example.com", role=UserRole.ADMIN)

    assert tuple(diretorio_isolado()) == antes


@pytest.mark.parametrize("papel", SEM_PERMISSAO)
def test_papel_sem_permissao_nao_altera_status_de_usuario(diretorio_isolado, papel):
    """Ativar/desativar é da mesma alçada de atribuir perfil."""
    alvo = conta_por_papel(UserRole.SELLER)
    antes = tuple(diretorio_isolado())

    with pytest.raises(PermissionDeniedError):
        backend.set_user_active(sessao(papel), alvo.user_id, False)

    assert tuple(diretorio_isolado()) == antes
