"""H09 — a consulta cronológica do histórico, pelo caminho do usuário.

O que esta história entrega não é "a tabela existe": é que a mudança de
preço e custo fique RECUPERÁVEL, em ordem, por quem tem alçada para ver. Daí
os três eixos aqui — quem alcança a consulta, em que ordem ela responde, e se
o que o usuário acabou de fazer aparece nela.
"""

import pytest
from PySide6.QtWidgets import QMessageBox

from stockflow.domain.enums.price_edit_field import PriceEditField
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.presentation import backend
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.windows.main_window import MainWindow

AREA = "historico_precos"


@pytest.fixture
def janela(qapp, monkeypatch):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setattr(backend, "_demo_users", {})
    monkeypatch.setattr(
        QMessageBox, "critical", staticmethod(lambda *args, **kwargs: None)
    )
    abertas = []

    def abrir(papel):
        w = MainWindow(session=conta_por_papel(papel).session())
        abertas.append(w)
        return w

    yield abrir
    for w in abertas:
        w.close()


def linhas_da_tabela(page):
    return [
        [
            page.table.item(linha, coluna).text()
            for coluna in range(page.table.columnCount())
        ]
        for linha in range(page.table.rowCount())
    ]


# --------------------------------------------------------------- 1. alçada


def test_o_admin_alcanca_o_historico(janela):
    w = janela(UserRole.ADMIN)

    assert w.sidebar.buttons[AREA].isVisibleTo(w.sidebar)
    assert w.page_widgets[AREA] is w.historico_precos_page


@pytest.mark.parametrize("papel", [UserRole.STOCK, UserRole.SELLER])
def test_quem_nao_e_admin_nao_ve_o_item_no_menu(papel, janela):
    """A tabela é restrita ao ADMIN pela policy; o menu não pode prometer mais."""
    w = janela(papel)

    assert not w.sidebar.buttons[AREA].isVisibleTo(w.sidebar)


@pytest.mark.parametrize("papel", [UserRole.STOCK, UserRole.SELLER])
def test_quem_nao_e_admin_e_recusado_mesmo_burlando_o_menu(papel, janela):
    """Esconder o botão é conforto, não controle."""
    w = janela(papel)

    with pytest.raises(PermissionDeniedError):
        w.price_history_service.list_changes(w.session)


# ---------------------------------------------------------------- 2. ordem


def test_a_consulta_responde_do_mais_recente_para_o_mais_antigo(janela):
    w = janela(UserRole.ADMIN)

    datas = [m.changed_on for m in w.price_history_service.list_changes(w.session)]

    assert datas == sorted(datas, reverse=True)


def test_a_tela_abre_com_o_historico_carregado(janela):
    """Histórico que só aparece depois de um clique não é consulta."""
    w = janela(UserRole.ADMIN)

    assert w.historico_precos_page.table.rowCount() > 0


# ------------------------------------------------------------- 3. conteúdo


def test_a_linha_mostra_de_onde_para_onde_o_valor_foi(janela):
    w = janela(UserRole.ADMIN)
    page = w.historico_precos_page

    cabecalho = [
        page.table.horizontalHeaderItem(c).text()
        for c in range(page.table.columnCount())
    ]
    assert cabecalho == ["Quando", "Produto", "Campo", "De", "Para", "Por"]
    assert any("R$" in linha[4] for linha in linhas_da_tabela(page))


def test_valor_que_nao_existia_antes_aparece_como_ausencia(janela):
    """"De R$ 0,00" seria o custo inventado que o banco se recusa a gravar."""
    w = janela(UserRole.ADMIN)
    page = w.historico_precos_page

    sem_anterior = [
        linha for linha in linhas_da_tabela(page)
        if linha[2] == PriceEditField.BUY_PRICE.label and linha[3] == "—"
    ]

    assert sem_anterior, "a semente não cobre o custo informado pela primeira vez"
    assert all("0,00" not in linha[3] for linha in sem_anterior)


# ---------------------------------------------------------------- 4. filtro


def test_o_filtro_por_produto_reduz_a_consulta(janela):
    w = janela(UserRole.ADMIN)
    page = w.historico_precos_page
    total = page.table.rowCount()

    codigo = linhas_da_tabela(page)[0][1].split(" — ")[0]
    page.produto_combo.setCurrentIndex(page.produto_combo.findData(codigo))

    assert page.table.rowCount() <= total
    assert all(linha[1].startswith(codigo) for linha in linhas_da_tabela(page))


def test_voltar_para_todos_restaura_a_consulta_inteira(janela):
    w = janela(UserRole.ADMIN)
    page = w.historico_precos_page
    total = page.table.rowCount()

    codigo = linhas_da_tabela(page)[0][1].split(" — ")[0]
    page.produto_combo.setCurrentIndex(page.produto_combo.findData(codigo))
    page.produto_combo.setCurrentIndex(page.produto_combo.findData(None))

    assert page.table.rowCount() == total


# ------------------------------------------------- 5. ponta a ponta no app


def test_editar_o_preco_pela_tela_aparece_no_historico(janela):
    """O elo que fecha a história: o que o usuário fez vira consulta.

    Vai pelo serviço de produto, e não gravando o rastro à mão: o que
    interessa provar é que o caminho REAL de edição deixa rastro, do mesmo
    jeito que o trigger faz no banco.
    """
    from dataclasses import replace

    w = janela(UserRole.ADMIN)
    codigo = next(iter(w.products))
    atual = w.products[codigo]

    w.product_service.update_product(
        w.session, codigo, _entrada(atual, sale_price="R$ 999,00")
    )
    w._carregar_historico_precos()

    primeira = linhas_da_tabela(w.historico_precos_page)[0]
    assert primeira[1].startswith(codigo)
    assert primeira[2] == PriceEditField.SELL_PRICE.label
    assert "999,00" in primeira[4]


def _entrada(produto, **mudancas):
    from stockflow.application.dto.product_input import ProductInput

    campos = dict(
        code=produto.code, name=produto.name, category=produto.category,
        unit=produto.unit, sale_price=produto.sale_price, cost=produto.cost,
        stock=produto.stock, active=produto.active,
    )
    campos.update(mudancas)
    return ProductInput(**campos)
