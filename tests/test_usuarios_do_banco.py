"""A tela de Usuários trocando a demonstração pelos dados da empresa.

O sintoma que motivou esta história: um usuário criado de verdade no Supabase
não aparecia na tela, porque a `UserTable` lia uma tupla fixa de
`demo_data.py` e nada no código chamava `fn_list_company_users`.

Dois cuidados que estes testes protegem, e que são fáceis de perder numa
refatoração:

1. A carga é SOB DEMANDA. `fn_list_company_users` recusa quem não é ADMIN,
   então buscar durante a construção da janela mataria a sessão de um SELLER
   ao montar uma tela que ele nem pode abrir.
2. Repovoar a tabela NÃO pode devolver o botão "Editar" a quem não é ADMIN —
   um QPushButton nasce habilitado, e foi exatamente esse o bug da
   `StockTable` na US01.
"""

import pytest
from PySide6.QtWidgets import QMessageBox

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation import backend
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.pages.users import UsersPage
from stockflow.presentation.windows.main_window import MainWindow

DO_BANCO = (
    ("Miguel", "teste.stockflow@gmail.com", "TI", "Administrador",
     "Ativo", "Hoje, 09:14", "#8129FF"),
    ("joana", "joana", "—", "Estoque", "Pendente", "Nunca", "#195BFF"),
)


def sessao(papel=UserRole.ADMIN, company_id="empresa-1"):
    base = conta_por_papel(papel).session()
    return type(base)(
        user_id=base.user_id, name=base.name, email=base.email,
        role=base.role, company_id=company_id,
    )


@pytest.fixture
def sem_dialogos(monkeypatch):
    avisos = []
    for nome in ("critical", "warning", "information"):
        monkeypatch.setattr(
            QMessageBox, nome,
            staticmethod(lambda *a, _n=nome, **k: avisos.append((_n, a[1:3]))),
        )
    return avisos


@pytest.fixture
def janela(qapp, request):
    abertas = []

    def criar(sessao_do_teste=None):
        window = MainWindow(sessao_do_teste)
        abertas.append(window)
        return window

    request.addfinalizer(lambda: [w.close() for w in abertas])
    return criar


# ------------------------------------------------------------ página isolada


def test_pagina_sem_argumento_continua_na_demonstracao(qapp):
    page = UsersPage()
    try:
        assert page.user_table.table.rowCount() == len(page.users)
        assert "Dados demonstrativos" in page.subtitle.text()
    finally:
        page.close()


def test_load_users_troca_a_lista_e_assume_a_origem(qapp):
    page = UsersPage()
    try:
        page.load_users(DO_BANCO)

        assert page.user_table.users == DO_BANCO
        assert page.user_table.table.rowCount() == 2
        assert page.subtitle.text() == "2 usuários · Dados da empresa"
    finally:
        page.close()


def test_empresa_sem_usuarios_mostra_lista_vazia(qapp):
    """Zero é resposta do banco, não falha de carregamento."""
    page = UsersPage()
    try:
        page.load_users(())
        assert page.user_table.table.rowCount() == 0
        assert page.subtitle.text() == "0 usuários · Dados da empresa"
    finally:
        page.close()


def test_o_filtro_de_perfil_segue_os_dados_carregados(qapp):
    """Filtrar por um perfil que ninguém tem devolve tabela vazia sem explicação."""
    page = UsersPage()
    try:
        page.load_users(DO_BANCO)
        perfis = [page.role_filter.itemText(i) for i in range(page.role_filter.count())]

        assert perfis[0] == "Todos os perfis"
        assert set(perfis[1:]) == {"Administrador", "Estoque"}
        assert "Gerente" not in perfis       # só existe na demonstração
    finally:
        page.close()


def test_repovoar_nao_devolve_editar_a_quem_nao_pode(qapp):
    """Regressão de segurança: botão novo nasce habilitado."""
    page = UsersPage()
    try:
        page.apply_permission(False)
        page.load_users(DO_BANCO)

        assert page.user_table.edit_buttons, "a recarga não pode deixar linhas sem ações"
        assert not any(b.isEnabled() for b in page.user_table.edit_buttons)
    finally:
        page.close()


def test_repovoar_mantem_o_widget_da_tabela(qapp):
    """`MainWindow` e os testes guardam `page.user_table` e conectam sinais nele."""
    page = UsersPage()
    try:
        antes = page.user_table
        recebidos = []
        page.user_table.venda_requested.connect(recebidos.append)

        page.load_users(DO_BANCO)

        assert page.user_table is antes
        page.user_table.venda_requested.emit("Miguel")
        assert recebidos == ["Miguel"]
    finally:
        page.close()


# ----------------------------------------------------- carga sob demanda


def test_sem_banco_a_janela_nao_busca_nada(janela, monkeypatch):
    monkeypatch.delenv(backend.BACKEND_VAR, raising=False)
    chamadas = []
    monkeypatch.setattr(
        "stockflow.presentation.windows.main_window.build_user_directory",
        lambda s: chamadas.append(s) or None,
    )
    window = janela(sessao())
    window.show_page("usuarios")

    # A função é consultada, mas devolve None: a tela fica na demonstração.
    assert "Dados demonstrativos" in window.users_page.subtitle.text()
    assert chamadas == [window.session]


def test_a_busca_so_acontece_ao_abrir_a_tela(janela, monkeypatch):
    """Construir a janela não pode custar uma ida à rede de administração."""
    chamadas = []
    monkeypatch.setattr(
        "stockflow.presentation.windows.main_window.build_user_directory",
        lambda s: chamadas.append(s) or DO_BANCO,
    )
    window = janela(sessao())
    assert chamadas == [], "a janela buscou usuários antes de alguém pedir a tela"

    window.show_page("usuarios")
    assert len(chamadas) == 1
    assert window.users_page.user_table.users == DO_BANCO


def test_a_busca_nao_se_repete_a_cada_visita(janela, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "stockflow.presentation.windows.main_window.build_user_directory",
        lambda s: chamadas.append(s) or DO_BANCO,
    )
    window = janela(sessao())
    for _ in range(3):
        window.show_page("usuarios")
        window.show_page("estoque")

    assert len(chamadas) == 1


def test_vendedor_barrado_nao_chega_a_buscar(janela, sem_dialogos, monkeypatch):
    """A guarda de permissão vem ANTES da rede.

    `fn_list_company_users` recusaria o SELLER de qualquer forma, mas gastar a
    requisição para ouvir "não" é pedir à tela que descubra o que a política
    já sabe.
    """
    chamadas = []
    monkeypatch.setattr(
        "stockflow.presentation.windows.main_window.build_user_directory",
        lambda s: chamadas.append(s) or DO_BANCO,
    )
    window = janela(sessao(UserRole.SELLER))

    assert window.show_page("usuarios") is False
    assert chamadas == []


def test_falha_na_busca_avisa_e_preserva_a_tela(janela, sem_dialogos, monkeypatch):
    """Rede fora não pode deixar a tela de usuários em branco e sem explicação."""
    def explodir(_sessao):
        raise RuntimeError("conexão recusada")

    monkeypatch.setattr(
        "stockflow.presentation.windows.main_window.build_user_directory", explodir
    )
    window = janela(sessao())

    assert window.show_page("usuarios") is True
    assert isinstance(window.last_users_error, RuntimeError)
    assert sem_dialogos, "a falha precisa aparecer para o usuário"
    assert window.users_page.user_table.table.rowCount() > 0


def test_relogin_descarta_o_diretorio_do_usuario_anterior(janela, monkeypatch):
    """Outra sessão pode ser outra empresa — a lista antiga seria vazamento."""
    chamadas = []
    monkeypatch.setattr(
        "stockflow.presentation.windows.main_window.build_user_directory",
        lambda s: chamadas.append(s.company_id) or DO_BANCO,
    )
    window = janela(sessao(company_id="empresa-1"))
    window.show_page("usuarios")

    window.apply_session(sessao(company_id="empresa-2"))
    window.show_page("usuarios")

    assert chamadas == ["empresa-1", "empresa-2"]
