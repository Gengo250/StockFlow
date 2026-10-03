"""US01 - a metade autorizada do critério de aceite.

`test_us01_permissao_produto.py` cobre a recusa; aqui o alvo é o caminho de
quem PODE gravar, percorrido como o usuário percorre: clicar em "Novo
Produto", digitar nos campos visíveis e clicar em salvar.

O detalhe que faz esses testes valerem alguma coisa: o cadastro NUNCA escreve
em `code_input`. O campo é somente leitura na tela, então um teste que o
preenche à mão prova apenas que a gravação funciona com um código que o
usuário real não tem como fornecer.
"""

import pytest
from PySide6.QtWidgets import QMessageBox

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_product_repository import (
    next_product_code,
)
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.demo_products import Product
from stockflow.presentation.windows.main_window import MainWindow


def sessao(papel):
    return conta_por_papel(papel).session()


@pytest.fixture
def sem_dialogos(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda *args, **kwargs: chamadas.append(args)),
    )
    return chamadas


@pytest.fixture
def janela(qapp, request):
    abertas = []

    def criar(sessao_do_teste=None):
        window = MainWindow(sessao_do_teste)
        abertas.append(window)
        window.show()
        return window

    request.addfinalizer(lambda: [w.close() for w in abertas])
    return criar


def escolher_categoria(page, categoria):
    """Seleciona a categoria como o usuário faria no combo."""
    if page.category_input.findText(categoria) < 0:
        page.category_input.addItem(categoria)
    page.category_input.setCurrentText(categoria)


def preencher_sem_tocar_no_codigo(page, nome, categoria="Eletrônicos",
                                  venda=99.90, estoque=7):
    page.name_input.setText(nome)
    escolher_categoria(page, categoria)
    page.sale_price_input.setValue(venda)
    page.initial_stock_input.setValue(estoque)


# ------------------------------------------------ geração de código (SKU)


def test_codigo_seguinte_do_catalogo_de_demonstracao():
    catalogo = {"PRD-007": None, "PRD-008": None, "PRD-009": None}
    assert next_product_code(catalogo) == "PRD-010"


def test_codigo_seguinte_com_catalogo_vazio():
    assert next_product_code({}) == "PRD-001"


def test_codigo_seguinte_nao_reaproveita_buraco_na_numeracao():
    # PRD-002 foi retirado do catálogo; devolvê-lo faria o código novo apontar
    # para o histórico de um produto que já existiu.
    assert next_product_code({"PRD-001": None, "PRD-003": None}) == "PRD-004"


def test_codigo_seguinte_ignora_codigo_fora_do_padrao():
    assert next_product_code({"AVULSO": None, "PRD-012": None}) == "PRD-013"


# ----------------------------------------------------- cadastro autorizado


@pytest.mark.parametrize("papel", [UserRole.ADMIN, UserRole.STOCK])
def test_cadastro_pelo_caminho_do_usuario_nao_depende_do_campo_de_codigo(
    janela, sem_dialogos, papel
):
    window = janela(sessao(papel))
    antes = set(window.products)

    window.estoque_page.new_product_button.click()
    page = window.novo_produto_page
    preencher_sem_tocar_no_codigo(page, "Webcam 4K", venda=499.0, estoque=30)
    codigo_na_tela = page.code_input.text()
    page.save_button.click()

    assert window.last_save_error is None
    novos = set(window.products) - antes
    assert len(novos) == 1
    codigo = novos.pop()
    assert codigo == codigo_na_tela
    assert codigo not in antes
    criado = window.products[codigo]
    assert criado.name == "Webcam 4K"
    assert criado.sale_price == "R$ 499,00"
    assert criado.stock == "30"


def test_formulario_carrega_apenas_catalogo_ativo(janela):
    window = janela(sessao(UserRole.ADMIN))

    window.estoque_page.new_product_button.click()

    assert window.novo_produto_page.category_input.count() == 3
    assert window.novo_produto_page.category_input.itemText(0) == "Selecione uma categoria"
    assert window.novo_produto_page.category_input.findText("Eletrônicos") >= 0
    assert window.novo_produto_page.category_input.findText("Periféricos") >= 0
    assert window.novo_produto_page.unit_input.findText("Unidade (UN)") >= 0


def test_dois_cadastros_seguidos_recebem_codigos_diferentes(janela, sem_dialogos):
    window = janela(sessao(UserRole.ADMIN))

    window.estoque_page.new_product_button.click()
    preencher_sem_tocar_no_codigo(window.novo_produto_page, "Webcam 4K")
    primeiro = window.novo_produto_page.code_input.text()
    window.novo_produto_page.save_button.click()

    window.estoque_page.new_product_button.click()
    preencher_sem_tocar_no_codigo(window.novo_produto_page, "Headset USB")
    segundo = window.novo_produto_page.code_input.text()
    window.novo_produto_page.save_button.click()

    assert window.last_save_error is None
    assert primeiro != segundo
    assert window.products[primeiro].name == "Webcam 4K"
    assert window.products[segundo].name == "Headset USB"


def test_formulario_de_cadastro_abre_limpo_depois_de_uma_tentativa(janela):
    window = janela(sessao(UserRole.ADMIN))
    page = window.novo_produto_page

    window.estoque_page.new_product_button.click()
    preencher_sem_tocar_no_codigo(page, "Rascunho esquecido", venda=12.0, estoque=5)
    page.description_input.setPlainText("texto antigo")
    page.cancel_button.click()

    window.estoque_page.new_product_button.click()

    assert page.name_input.text() == ""
    assert page.description_input.toPlainText() == ""
    assert page.sale_price_input.value() == 0
    assert page.cost_price_input.value() == 0
    assert page.initial_stock_input.value() == 0
    assert page.category_input.currentIndex() == 0
    assert page.product_status_toggle.isChecked()


# ------------------------------------------------------ edição autorizada


def test_edicao_de_estoque_preserva_custo_unidade_e_categoria(janela, sem_dialogos):
    window = janela(sessao(UserRole.ADMIN))
    antes = window.products["PRD-009"]

    window.estoque_page.stock_table.edit_buttons[0].click()
    page = window.editar_produto_page
    assert page.code_input.text() == "PRD-009"
    page.initial_stock_input.setValue(42)
    page.save_button.click()

    assert window.last_save_error is None
    depois = window.products["PRD-009"]
    assert depois.stock == "42"
    assert depois.cost == antes.cost
    assert depois.unit == antes.unit
    assert depois.category == antes.category
    assert depois.name == antes.name
    assert depois.sale_price == antes.sale_price


def test_edicao_nao_reativa_produto_inativo(janela, sem_dialogos):
    window = janela(sessao(UserRole.ADMIN))
    inativo = Product("PRD-050", "Impressora antiga", "Eletrônicos",
                      "Unidade (UN)", "R$ 100,00", "R$ 60,00", False, "5", "Crítico")
    window.products[inativo.code] = inativo

    # Mesma tupla de 6 campos que a tabela de Estoque emite.
    window._show_edit_product((inativo.code, inativo.name, inativo.category,
                               inativo.stock, inativo.sale_price,
                               inativo.stock_status))
    page = window.editar_produto_page
    assert not page.product_status_toggle.isChecked()
    page.initial_stock_input.setValue(9)
    page.save_button.click()

    assert window.last_save_error is None
    assert window.products["PRD-050"].active is False


def test_edicao_com_categoria_nao_selecionada_exibe_erro_e_nao_grava(
    janela, sem_dialogos
):
    window = janela(sessao(UserRole.ADMIN))
    antes = window.products["PRD-009"]

    window.estoque_page.stock_table.edit_buttons[0].click()
    page = window.editar_produto_page
    page.category_input.setCurrentIndex(0)
    page.save_button.click()

    assert isinstance(window.last_save_error, ValueError)
    assert "Categoria é obrigatória" in str(window.last_save_error)
    assert window.products["PRD-009"] == antes
    assert sem_dialogos


def test_duas_edicoes_do_mesmo_produto_nao_se_apagam(janela, sem_dialogos):
    window = janela(sessao(UserRole.ADMIN))

    window.estoque_page.stock_table.edit_buttons[0].click()
    page = window.editar_produto_page
    page.name_input.setText("Monitor 2026")
    page.save_button.click()

    window.estoque_page.stock_table.edit_buttons[0].click()
    assert page.name_input.text() == "Monitor 2026"
    page.sale_price_input.setValue(1999.0)
    page.save_button.click()

    assert window.last_save_error is None
    atualizado = window.products["PRD-009"]
    assert atualizado.name == "Monitor 2026"
    assert atualizado.sale_price == "R$ 1.999,00"


# ------------------------------------------------- reflexo na tela de Produtos


def test_tela_de_produtos_mostra_o_produto_cadastrado(janela, sem_dialogos):
    window = janela(sessao(UserRole.ADMIN))
    window.products_page.new_product_button.click()
    preencher_sem_tocar_no_codigo(window.novo_produto_page, "Webcam 4K")
    codigo = window.novo_produto_page.code_input.text()
    window.novo_produto_page.save_button.click()

    assert window.last_save_error is None
    assert codigo in window.products
    assert codigo in window.products_page.cards


def test_tela_de_produtos_reflete_a_edicao_e_mantem_a_busca(janela, sem_dialogos):
    window = janela(sessao(UserRole.ADMIN))
    window.products_page.search_input.setText("monitor")

    window.estoque_page.stock_table.edit_buttons[0].click()
    window.editar_produto_page.name_input.setText("Monitor 2026")
    window.editar_produto_page.save_button.click()

    assert window.products_page.search_input.text() == "monitor"
    card = window.products_page.cards["PRD-009"]
    assert card.accessibleName() == "Ver detalhes de Monitor 2026"


# --------------------------------------------------- sessão ausente (fechado)


def test_janela_sem_sessao_nao_libera_escrita(janela):
    window = janela()
    assert not window.novo_produto_page.save_button.isEnabled()
    assert not window.editar_produto_page.save_button.isEnabled()
    assert not window.estoque_page.new_product_button.isEnabled()
    assert not window.products_page.new_product_button.isEnabled()
    assert not any(b.isEnabled() for b in window.estoque_page.stock_table.edit_buttons)


def test_janela_sem_sessao_recusa_gravacao_forcada(janela, sem_dialogos):
    window = janela()
    antes = dict(window.products)
    window.pages.setCurrentWidget(window.novo_produto_page)
    preencher_sem_tocar_no_codigo(window.novo_produto_page, "Webcam 4K")

    window.novo_produto_page.save_button.setEnabled(True)
    window.novo_produto_page.save_button.click()

    assert isinstance(window.last_save_error, PermissionDeniedError)
    assert window.products == antes
