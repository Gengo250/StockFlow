"""Primeira categoria da empresa, pela interface.

`fn_create_categories` existe no banco desde o começo, mas nada no aplicativo
a chamava: o combo de categoria do formulário só era preenchido por leitura.
Numa empresa recém-criada ele vinha com o placeholder e mais nada, e o
cadastro de produto exige categoria — então o primeiro produto era
impossível de cadastrar pela tela. Foi o que travou o roteiro de aceite real
contra o Supabase em 05/10/2026.
"""

import pytest

from stockflow.application.dto.product_input import ProductInput
from stockflow.application.services.product_service import ProductService
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.presentation.demo_accounts import conta_por_papel


def sessao(papel=UserRole.ADMIN):
    return conta_por_papel(papel).session()


@pytest.fixture
def servico():
    """Empresa sem nenhuma categoria: o estado que travava o cadastro."""
    return ProductService(DemoProductRepository({}, active_categories=()))


def test_empresa_sem_categoria_ganha_a_primeira_pela_interface(servico):
    assert servico.list_categories() == ()

    servico.create_category(sessao(), "Eletrônicos")

    assert servico.list_categories() == ("Eletrônicos",)


def test_categoria_criada_passa_a_valer_para_o_cadastro_de_produto(servico):
    """Criar e não poder usar seria o mesmo impasse com outra mensagem."""
    servico.create_category(sessao(), "Periféricos")

    servico.create_product(sessao(), ProductInput(
        code="PRD-900", name="Teclado mecânico", category="Periféricos",
        unit="Unidade (UN)", sale_price="R$ 459,90", cost="R$ 280,00",
        stock="7", active=True,
    ))

    assert servico._repository.get("PRD-900").category == "Periféricos"


def test_nome_vazio_e_recusado(servico):
    with pytest.raises(ValueError):
        servico.create_category(sessao(), "   ")


def test_nome_e_gravado_sem_espacos_nas_bordas(servico):
    servico.create_category(sessao(), "  Ferramentas  ")

    assert servico.list_categories() == ("Ferramentas",)


def test_categoria_repetida_e_recusada_antes_de_ir_ao_banco(servico):
    """`categories` é UNIQUE (company_id, name); a recusa vem com mensagem."""
    servico.create_category(sessao(), "Eletrônicos")

    with pytest.raises(ValueError):
        servico.create_category(sessao(), "Eletrônicos")


def test_repeticao_ignora_caixa_e_espacos(servico):
    servico.create_category(sessao(), "Eletrônicos")

    with pytest.raises(ValueError):
        servico.create_category(sessao(), "  eletrônicos ")


@pytest.mark.parametrize("papel", [UserRole.SELLER])
def test_papel_sem_permissao_nao_cria_categoria(servico, papel):
    """Mesma regra de `fn_create_categories`: só ADMIN e STOCK."""
    with pytest.raises(PermissionDeniedError):
        servico.create_category(sessao(papel), "Eletrônicos")

    assert servico.list_categories() == ()


def test_sessao_ausente_nao_cria_categoria(servico):
    with pytest.raises(PermissionDeniedError):
        servico.create_category(None, "Eletrônicos")


def test_papel_de_estoque_cria_categoria(servico):
    servico.create_category(sessao(UserRole.STOCK), "Eletrônicos")

    assert servico.list_categories() == ("Eletrônicos",)


# ------------------------------------------------------------------ na tela

@pytest.fixture
def janela(qapp):
    from stockflow.presentation.windows.main_window import MainWindow

    window = MainWindow(sessao())
    yield window
    window.close()


def test_formulario_oferece_o_botao_de_nova_categoria(janela):
    assert janela.novo_produto_page.new_category_button.isEnabled()
    assert janela.editar_produto_page.new_category_button.isEnabled()


def test_papel_sem_permissao_nao_ve_o_botao_habilitado(qapp):
    from stockflow.presentation.windows.main_window import MainWindow

    window = MainWindow(sessao(UserRole.SELLER))
    try:
        assert not window.novo_produto_page.new_category_button.isEnabled()
    finally:
        window.close()


def test_categoria_cadastrada_pela_tela_entra_no_combo_ja_selecionada(janela, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    page = janela.novo_produto_page
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Climatização", True)))

    assert page.category_input.findText("Climatização") < 0

    janela._cadastrar_categoria(page)

    assert page.category_input.currentText() == "Climatização"
    assert "Climatização" in janela.product_repository.list_active_categories()


def test_desistir_do_dialogo_nao_cadastra_nada(janela, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    page = janela.novo_produto_page
    antes = janela.product_repository.list_active_categories()
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Climatização", False)))

    assert janela._cadastrar_categoria(page) is None
    assert janela.product_repository.list_active_categories() == antes


def test_erro_de_cadastro_nao_mexe_no_formulario(janela, monkeypatch):
    """Nome repetido avisa e deixa o resto do formulário como estava."""
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    page = janela.novo_produto_page
    page.name_input.setText("Produto em edição")
    existente = janela.product_repository.list_active_categories()[0]
    avisos = []
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (existente, True)))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: avisos.append(a)))

    assert janela._cadastrar_categoria(page) is None
    assert avisos, "a recusa precisa ser explicada"
    assert page.name_input.text() == "Produto em edição"


def test_cadastrar_categoria_preserva_o_resto_do_formulario(janela, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    page = janela.novo_produto_page
    page.name_input.setText("Ar-condicionado")
    page.initial_stock_input.setValue(12)
    unidade = page.unit_input.currentText()
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Climatização", True)))

    janela._cadastrar_categoria(page)

    assert page.name_input.text() == "Ar-condicionado"
    assert page.initial_stock_input.value() == 12
    assert page.unit_input.currentText() == unidade
