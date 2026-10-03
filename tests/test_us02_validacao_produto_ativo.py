"""US02 - produto inativo não entra em operação nova; o histórico não muda.

Dois critérios, e eles puxam para lados opostos:

1. Uma venda NOVA só aceita produto ativo. A oferta do combo esconde o
   inativo, e a gravação revalida — o combo é uma foto, e o Estoque pode
   desativar o produto com a tela de Vendas aberta.
2. Uma venda JÁ REGISTRADA continua exibindo o produto que foi associado a
   ela. O vínculo é do passado; desativar o cadastro depois não reescreve o
   que aconteceu. Por isso o histórico guarda o nome gravado na hora e não
   relê o catálogo.

`VND-1001` referencia de propósito um produto que nem existe mais no
catálogo: se o histórico dependesse da leitura do cadastro, essa linha
apareceria vazia.
"""

import pytest
from PySide6.QtWidgets import QMessageBox

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.demo_products import DEMO_PRODUCTS, Product
from stockflow.presentation.pages.vendas import VendasPage
from stockflow.presentation.windows.main_window import MainWindow

CLIENTE_COLUMN = 1
PRODUTO_COLUMN = 2


@pytest.fixture
def catalogo():
    """Cópia do catálogo demonstrativo: o teste desativa produtos nele."""
    return dict(DEMO_PRODUCTS)


@pytest.fixture
def vendas(qapp, catalogo):
    return VendasPage(products=catalogo)


def desativar(catalogo, code):
    atual = catalogo[code]
    catalogo[code] = Product(
        code=atual.code, name=atual.name, category=atual.category,
        unit=atual.unit, sale_price=atual.sale_price, cost=atual.cost,
        active=False, stock=atual.stock, stock_status=atual.stock_status,
    )


def itens_do_combo(combo):
    return [combo.itemText(i) for i in range(combo.count())]


def linha_do_produto(page, code):
    for row in range(page.table.rowCount()):
        if page.table.item(row, 0).text() == code:
            return row
    raise AssertionError(f"Produto {code} não encontrado na tabela de estoque.")


def coluna(page, column):
    return [page.table.item(r, column).text() for r in range(page.table.rowCount())]


def venda_valida(page, cliente="Ana Ferreira", produto="PRD-009", valor="100,00"):
    page.selecionar_cliente_externo(cliente)
    page.selecionar_produto(produto)
    page.val_input.setText(valor)
    page._registrar_venda()


# --------------------------------------------- oferta: só o que está ativo

def test_combo_de_produtos_comeca_no_placeholder(vendas):
    assert itens_do_combo(vendas.produto_combo)[0] == "Selecione um produto..."
    assert vendas.produto_combo.currentData() is None


def test_combo_lista_os_produtos_ativos_do_catalogo(vendas):
    textos = itens_do_combo(vendas.produto_combo)
    assert any("PRD-009" in t for t in textos)
    assert any("Teclado mecânico sem fio" in t for t in textos)


def test_produto_desativado_some_da_oferta_apos_recarga(vendas, catalogo):
    desativar(catalogo, "PRD-008")
    vendas.reload_products()

    assert not any("PRD-008" in t for t in itens_do_combo(vendas.produto_combo))
    assert any("PRD-009" in t for t in itens_do_combo(vendas.produto_combo))


def test_produto_reativado_volta_para_a_oferta(vendas, catalogo):
    desativar(catalogo, "PRD-008")
    vendas.reload_products()
    catalogo["PRD-008"] = DEMO_PRODUCTS["PRD-008"]
    vendas.reload_products()

    assert any("PRD-008" in t for t in itens_do_combo(vendas.produto_combo))


def test_recarregar_produtos_nao_duplica_itens(vendas):
    antes = vendas.produto_combo.count()
    vendas.reload_products()
    assert vendas.produto_combo.count() == antes


# ------------------------------------------ seleção por código, com aviso

def test_selecionar_produto_ativo(vendas):
    assert vendas.selecionar_produto("PRD-007") is True
    assert vendas.produto_combo.currentData()["codigo"] == "PRD-007"
    assert vendas.warning_label.text() == ""


def test_selecionar_produto_inativo_e_recusado_com_aviso(vendas, catalogo):
    desativar(catalogo, "PRD-007")
    vendas.reload_products()

    assert vendas.selecionar_produto("PRD-007") is False
    assert "inativo" in vendas.warning_label.text().lower()
    assert vendas.produto_combo.currentData() is None


def test_produto_inexistente_nao_e_relatado_como_inativo(vendas):
    assert vendas.selecionar_produto("PRD-404") is False
    aviso = vendas.warning_label.text().lower()
    assert "não existe" in aviso
    assert "inativo" not in aviso


# ---------------------------------------------- gravação de venda nova

def test_venda_sem_produto_e_bloqueada(vendas):
    vendas.selecionar_cliente_externo("Ana Ferreira")
    vendas.val_input.setText("100,00")
    vendas._registrar_venda()

    assert len(vendas.historico_vendas) == 2
    assert vendas.warning_label.text() == "Selecione um produto ativo válido."


def test_venda_valida_grava_codigo_e_nome_do_produto(vendas):
    venda_valida(vendas, produto="PRD-009", valor="250,00")

    nova = vendas.historico_vendas[0]
    assert nova["produto_codigo"] == "PRD-009"
    assert nova["produto"] == 'Monitor LG UltraWide 34"'
    assert vendas.table.item(0, PRODUTO_COLUMN).text() == 'Monitor LG UltraWide 34"'


def test_produto_desativado_com_a_tela_aberta_e_recusado_na_gravacao(vendas, catalogo):
    """O combo é uma foto; a gravação revalida contra o catálogo vivo.

    Sem esta revalidação, bastava o Estoque desativar o produto depois que a
    tela de Vendas montou o combo para a venda passar assim mesmo.
    """
    vendas.selecionar_cliente_externo("Ana Ferreira")
    vendas.selecionar_produto("PRD-007")
    vendas.val_input.setText("80,00")

    desativar(catalogo, "PRD-007")
    vendas._registrar_venda()

    assert len(vendas.historico_vendas) == 2, "venda com produto inativo foi gravada"
    assert "inativo" in vendas.warning_label.text().lower()
    assert "PRD-007" in vendas.warning_label.text()


def test_recusa_por_produto_inativo_tira_ele_da_oferta(vendas, catalogo):
    vendas.selecionar_cliente_externo("Ana Ferreira")
    vendas.selecionar_produto("PRD-007")
    vendas.val_input.setText("80,00")

    desativar(catalogo, "PRD-007")
    vendas._registrar_venda()

    assert not any("PRD-007" in t for t in itens_do_combo(vendas.produto_combo))


def test_produto_sumido_do_catalogo_e_recusado_na_gravacao(vendas, catalogo):
    vendas.selecionar_cliente_externo("Ana Ferreira")
    vendas.selecionar_produto("PRD-007")
    vendas.val_input.setText("80,00")

    del catalogo["PRD-007"]
    vendas._registrar_venda()

    assert len(vendas.historico_vendas) == 2
    assert "não existe" in vendas.warning_label.text().lower()


def test_formulario_limpa_o_produto_apos_a_venda(vendas):
    venda_valida(vendas)
    assert vendas.produto_combo.currentIndex() == 0
    assert vendas.produto_combo.currentData() is None


# ------------------------------------------- histórico: o passado não muda

def test_historico_inicial_exibe_os_produtos_associados(vendas):
    assert coluna(vendas, PRODUTO_COLUMN) == [
        "Cabo HDMI 2m", "Mouse ergonômico",
    ]


def test_historico_preserva_produto_que_saiu_do_catalogo(vendas, catalogo):
    """VND-1001 aponta para PRD-004, que não está mais cadastrado."""
    assert "PRD-004" not in catalogo
    assert "Cabo HDMI 2m" in coluna(vendas, PRODUTO_COLUMN)


def test_desativar_produto_nao_apaga_a_venda_antiga(vendas, catalogo):
    desativar(catalogo, "PRD-007")
    vendas.reload_products()

    assert "Mouse ergonômico" in coluna(vendas, PRODUTO_COLUMN)
    assert coluna(vendas, CLIENTE_COLUMN) == ["Patrícia Lima", "Ana Ferreira"]


def test_desativar_produto_depois_da_venda_nao_reescreve_o_historico(vendas, catalogo):
    venda_valida(vendas, produto="PRD-008", valor="459,90")
    desativar(catalogo, "PRD-008")
    vendas.reload_products()

    assert vendas.table.item(0, PRODUTO_COLUMN).text() == "Teclado mecânico sem fio"
    assert vendas.historico_vendas[0]["produto_codigo"] == "PRD-008"


# -------------------------------------- integração: Estoque desativa, Vendas vê

@pytest.fixture
def sem_dialogos(monkeypatch):
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))


@pytest.fixture
def janela(qapp, request):
    abertas = []

    def criar(papel=UserRole.ADMIN):
        window = MainWindow(conta_por_papel(papel).session())
        abertas.append(window)
        return window

    request.addfinalizer(lambda: [w.close() for w in abertas])
    return criar


def test_vendas_compartilha_o_catalogo_da_janela(janela):
    window = janela()
    assert window.vendas_page.products is window.products


def test_desativar_pela_edicao_tira_o_produto_da_venda(janela, sem_dialogos):
    """Caminho real: ADMIN desativa no formulário, Vendas deixa de oferecer."""
    window = janela()
    assert any("PRD-009" in t for t in itens_do_combo(window.vendas_page.produto_combo))

    window.estoque_page.stock_table.edit_buttons[0].click()
    form = window.editar_produto_page
    assert form.code_input.text() == "PRD-009"
    form.product_status_toggle.setChecked(False)
    form.save_button.click()

    assert window.last_save_error is None
    assert window.products["PRD-009"].active is False
    assert not any(
        "PRD-009" in t for t in itens_do_combo(window.vendas_page.produto_combo)
    )


def test_reativar_pela_edicao_preserva_historico_e_retorna_a_selecao(
    janela, sem_dialogos
):
    """O status pode voltar a ativo sem apagar vendas já registradas."""
    window = janela()
    vendas = window.vendas_page
    historico_antes = [dict(venda) for venda in vendas.historico_vendas]

    window.estoque_page.stock_table.edit_buttons[0].click()
    form = window.editar_produto_page
    assert form.code_input.text() == "PRD-009"
    form.product_status_toggle.setChecked(False)
    form.save_button.click()

    assert window.last_save_error is None
    assert window.products["PRD-009"].active is False
    linha = linha_do_produto(window.estoque_page, "PRD-009")
    assert window.estoque_page.table.item(linha, 5).text() == "Normal"
    assert window.estoque_page.table.item(linha, 6).text() == "Inativo"
    assert not any("PRD-009" in t for t in itens_do_combo(vendas.produto_combo))
    assert vendas.historico_vendas == historico_antes
    window._show_product_details("PRD-009")
    assert window.product_details_page.values["active"].text() == "Inativo"

    window.estoque_page.stock_table.edit_buttons[0].click()
    form = window.editar_produto_page
    assert form.code_input.text() == "PRD-009"
    assert not form.product_status_toggle.isChecked()
    form.product_status_toggle.setChecked(True)
    form.save_button.click()

    assert window.last_save_error is None
    assert window.products["PRD-009"].active is True
    linha = linha_do_produto(window.estoque_page, "PRD-009")
    assert window.estoque_page.table.item(linha, 5).text() == "Normal"
    assert window.estoque_page.table.item(linha, 6).text() == "Ativo"
    assert any("PRD-009" in t for t in itens_do_combo(vendas.produto_combo))
    assert vendas.historico_vendas == historico_antes
    window._show_product_details("PRD-009")
    assert window.product_details_page.values["active"].text() == "Ativo"
