"""US01 - controle de permissão de produto na UI e na gravação.

O critério de aceite do cartão não é "o botão fica cinza": é que o papel sem
permissão não consiga gravar nem quando o controle visual é burlado. Por isso
os testes mais importantes aqui forçam `save_button.setEnabled(True)` e
exigem o catálogo intacto depois do clique.
"""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.app import LoginFlow
from stockflow.presentation.demo_accounts import (
    DEMO_ACCOUNTS,
    autenticar,
    conta_por_papel,
)
from stockflow.infrastructure.repositories.demo_product_repository import (
    DEFAULT_MINIMUM_STOCK,
    derive_stock_status,
)
from stockflow.presentation.windows.login_window import DEMO_EMAIL, DEMO_PASSWORD
from stockflow.presentation.windows.main_window import MainWindow


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
    monkeypatch.setattr(
        QMessageBox,
        "information",
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


def preencher_formulario(page, codigo, nome, estoque=18, venda=2499.90, custo=1850.0):
    page.code_input.setText(codigo)
    page.name_input.setText(nome)
    if page.category_input.findText("Eletrônicos") < 0:
        page.category_input.addItem("Eletrônicos")
    page.category_input.setCurrentText("Eletrônicos")
    page.initial_stock_input.setValue(estoque)
    page.sale_price_input.setValue(venda)
    page.cost_price_input.setValue(custo)


# ------------------------------------------------- papéis autorizados


@pytest.mark.parametrize("papel", [UserRole.ADMIN, UserRole.STOCK])
def test_papel_autorizado_ve_os_controles_de_escrita_liberados(janela, papel):
    window = janela(sessao(papel))
    for page in (window.novo_produto_page, window.editar_produto_page):
        assert page.save_button.isEnabled()
        assert page.permission_warning.isHidden()
    assert window.novo_produto_page.draft_button.isEnabled()
    assert window.estoque_page.new_product_button.isEnabled()
    assert window.products_page.new_product_button.isEnabled()
    assert all(b.isEnabled() for b in window.estoque_page.stock_table.edit_buttons)


@pytest.mark.parametrize("papel", [UserRole.ADMIN, UserRole.STOCK])
def test_papel_autorizado_cadastra_produto_no_catalogo(janela, sem_dialogos, papel):
    window = janela(sessao(papel))
    window.estoque_page.new_product_button.click()
    preencher_formulario(window.novo_produto_page, "PRD-100", "Webcam 4K", estoque=30)

    window.novo_produto_page.save_button.click()

    assert window.last_save_error is None
    criado = window.products["PRD-100"]
    assert criado.name == "Webcam 4K"
    assert criado.sale_price == "R$ 2.499,90"
    assert criado.cost == "R$ 1.850,00"
    assert criado.stock == "30"
    assert criado.stock_status == "Normal"
    assert window.pages.currentWidget() is window.estoque_page


@pytest.mark.parametrize("papel", [UserRole.ADMIN, UserRole.STOCK])
def test_papel_autorizado_edita_produto_existente(janela, sem_dialogos, papel):
    window = janela(sessao(papel))
    window.estoque_page.stock_table.edit_buttons[0].click()
    page = window.editar_produto_page
    assert page.code_input.text() == "PRD-009"
    page.name_input.setText("Monitor LG UltraWide 34 (2026)")
    page.initial_stock_input.setValue(4)

    page.save_button.click()

    assert window.last_save_error is None
    atualizado = window.products["PRD-009"]
    assert atualizado.name == "Monitor LG UltraWide 34 (2026)"
    assert atualizado.stock == "4"
    # 4 <= 10 -> Baixo, pela mesma regra de `fn_stock_state`. Só saldo ZERO é
    # Crítico; a regra antiga da UI, que chamava de crítico tudo abaixo da
    # metade do mínimo, divergia do banco e foi descartada.
    assert atualizado.stock_status == "Baixo"


# ------------------------------------------------- papel sem permissão


def test_vendedor_nao_recebe_controles_de_escrita(janela):
    window = janela(sessao(UserRole.SELLER))
    window.pages.setCurrentWidget(window.novo_produto_page)
    page = window.novo_produto_page

    assert not page.save_button.isEnabled()
    assert not page.draft_button.isEnabled()
    assert page.permission_warning.isVisible()
    assert not window.editar_produto_page.save_button.isEnabled()
    assert not window.estoque_page.new_product_button.isEnabled()
    assert not window.products_page.new_product_button.isEnabled()
    assert window.estoque_page.stock_table.edit_buttons
    assert not any(b.isEnabled() for b in window.estoque_page.stock_table.edit_buttons)


def test_vendedor_que_burla_o_botao_nao_cadastra_produto(janela, sem_dialogos):
    """Critério de aceite: a negação vive no serviço, não no `setEnabled`."""
    window = janela(sessao(UserRole.SELLER))
    antes = dict(window.products)
    window.pages.setCurrentWidget(window.novo_produto_page)
    preencher_formulario(window.novo_produto_page, "PRD-100", "Webcam 4K")

    window.novo_produto_page.save_button.setEnabled(True)
    window.novo_produto_page.save_button.click()

    assert isinstance(window.last_save_error, PermissionError)
    assert "PRD-100" not in window.products
    assert window.products == antes
    assert sem_dialogos, "o usuário precisa ver o motivo da recusa"


def test_vendedor_que_burla_o_botao_nao_edita_produto(janela, sem_dialogos):
    window = janela(sessao(UserRole.SELLER))
    antes = dict(window.products)

    editar = window.estoque_page.stock_table.edit_buttons[0]
    editar.setEnabled(True)
    editar.click()
    page = window.editar_produto_page
    page.name_input.setText("Nome adulterado")
    page.initial_stock_input.setValue(999)
    page.save_button.setEnabled(True)
    page.save_button.click()

    assert isinstance(window.last_save_error, PermissionError)
    assert window.products == antes
    assert window.products["PRD-009"].name == "Monitor LG UltraWide 34\""
    assert window.products["PRD-009"].stock == "18"


# ------------------------------------------------- login -> sessão


def test_login_emite_sessao_com_o_papel_de_cada_conta(qapp, tmp_path):
    for conta in DEMO_ACCOUNTS:
        settings = QSettings(f"{tmp_path}/{conta.role}.ini", QSettings.IniFormat)
        flow = LoginFlow(settings)
        try:
            sessoes = []
            flow.login.authenticated.connect(sessoes.append)
            flow.login.email_input.setText(f"  {conta.email.upper()}  ")
            flow.login.password_input.setText(conta.password)
            flow.login.submit_button.click()

            assert [s.role for s in sessoes] == [conta.role]
            assert sessoes[0].name == conta.name
            assert flow.main.session.role == conta.role
        finally:
            if flow.main is not None:
                flow.main.close()
            flow.login.close()


def test_credencial_errada_nao_emite_sessao(qapp, tmp_path):
    settings = QSettings(f"{tmp_path}/errada.ini", QSettings.IniFormat)
    flow = LoginFlow(settings)
    try:
        sessoes = []
        flow.login.authenticated.connect(sessoes.append)
        flow.login.email_input.setText(DEMO_EMAIL)
        flow.login.password_input.setText("senha errada")
        flow.login.submit_button.click()

        assert sessoes == []
        assert flow.main is None
        assert autenticar(DEMO_EMAIL, "senha errada") is None
        assert autenticar("ninguem@example.com", DEMO_PASSWORD) is None
    finally:
        flow.login.close()


def test_relogar_com_outra_conta_troca_as_permissoes_da_janela(qapp, tmp_path):
    """O furo que o cartão fecha: a janela do ADMIN sobrevivendo ao logout."""
    settings = QSettings(f"{tmp_path}/relogin.ini", QSettings.IniFormat)
    flow = LoginFlow(settings)
    try:
        flow.login.email_input.setText(DEMO_EMAIL)
        flow.login.password_input.setText(DEMO_PASSWORD)
        flow.login.submit_button.click()
        assert flow.main.session.role == UserRole.ADMIN
        assert flow.main.novo_produto_page.save_button.isEnabled()

        flow.main.sidebar.logout_button.click()

        vendedor = conta_por_papel(UserRole.SELLER)
        flow.login.email_input.setText(vendedor.email)
        flow.login.password_input.setText(vendedor.password)
        flow.login.submit_button.click()

        assert flow.main.session.role == UserRole.SELLER
        assert not flow.main.novo_produto_page.save_button.isEnabled()
        assert not flow.main.estoque_page.new_product_button.isEnabled()
    finally:
        if flow.main is not None:
            flow.main.close()
        flow.login.close()


# ------------------------------------------------- status do estoque


def test_status_do_estoque_nas_quatro_faixas():
    """Tradução literal de `public.fn_stock_state`.

    Se este teste e aquela função discordarem, a tela mostra uma situação e
    um relatório SQL mostra outra — foi exatamente o que aconteceu enquanto a
    UI tinha regra própria.
    """
    minimo = DEFAULT_MINIMUM_STOCK                      # 10
    assert derive_stock_status(0, minimo) == "Crítico"   # sem unidade em mãos
    assert derive_stock_status(1, minimo) == "Baixo"     # só o zero é crítico
    assert derive_stock_status(minimo, minimo) == "Baixo"      # IGUAL entra
    assert derive_stock_status(minimo + 1, minimo) == "Atenção"  # 11 < 12
    assert derive_stock_status(12, minimo) == "Normal"         # 12 >= 10×1,2


def test_produto_sem_minimo_configurado_nao_alerta():
    """Critério da US04: excluir produtos sem mínimo definido.

    Zero e ausente significam a mesma coisa, como o
    `COALESCE(ps.min_quantity, 0)` da `vw_stock_situation`.
    """
    assert derive_stock_status(1, 0) == "Normal"
    assert derive_stock_status(1, None) == "Normal"
    # Nem mesmo saldo zerado alerta sem limiar configurado.
    assert derive_stock_status(0, 0) == "Normal"
