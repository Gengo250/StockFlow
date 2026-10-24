"""Cancelar e devolver venda pela janela, com efeito no estoque (US17).

O critério que importa não é "a venda mudou de status": é que o saldo
acompanhou. Uma reversão que marca a venda e deixa o estoque baixado faria a
próxima venda ser recusada por mercadoria que voltou para a prateleira.
"""

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.windows.main_window import MainWindow

PRODUTO = "PRD-009"


@pytest.fixture
def sem_dialogos(monkeypatch):
    for nome in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, nome, staticmethod(lambda *a, **k: None))


def _janela(qapp, monkeypatch, tmp_path, papel=UserRole.ADMIN):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return MainWindow(conta_por_papel(papel).session())


@pytest.fixture
def janela(qapp, monkeypatch, tmp_path, sem_dialogos):
    window = _janela(qapp, monkeypatch, tmp_path)
    yield window
    window.close()


def _vender(window, quantidade=2):
    page = window.vendas_page
    page.recarregar_clientes_disponiveis()
    assert page._apontar_cliente(page.clientes[0]["id"])
    assert page.selecionar_produto(PRODUTO)
    page.qtd_input.setText(str(quantidade))
    page.save_button.click()
    assert not page.warning_label.text(), page.warning_label.text()
    return page.historico_vendas[0]["id"]


def test_cancelar_devolve_o_saldo_ao_estoque(janela):
    antes = int(janela.products[PRODUTO].stock)
    venda = _vender(janela)
    assert int(janela.products[PRODUTO].stock) == antes - 2

    janela._cancelar_venda(venda, "registro em duplicidade")

    assert int(janela.products[PRODUTO].stock) == antes


def test_devolver_devolve_o_saldo_ao_estoque(janela):
    antes = int(janela.products[PRODUTO].stock)
    venda = _vender(janela, quantidade=3)

    janela._devolver_venda(venda, "cliente desistiu")

    assert int(janela.products[PRODUTO].stock) == antes


def test_venda_cancelada_aparece_com_o_status_no_historico(janela):
    venda = _vender(janela)
    janela._cancelar_venda(venda, "engano")

    linha = next(
        v for v in janela.vendas_page.historico_vendas if v["id"] == venda
    )
    assert linha["status"] == "CANCELADA"


def test_vinculo_guarda_especie_motivo_e_fica_legivel(janela):
    venda = _vender(janela)
    janela._devolver_venda(venda, "produto com defeito")

    gravado = janela.sale_service.get_sale(janela.session, venda)
    assert gravado["status"] == "DEVOLVIDA"
    assert gravado["reversal_kind"] == "DEVOLUCAO"
    assert gravado["reversal_reason"] == "produto com defeito"


def test_reverter_duas_vezes_nao_mexe_no_saldo_de_novo(janela):
    venda = _vender(janela)
    janela._cancelar_venda(venda, "engano")
    depois_da_primeira = int(janela.products[PRODUTO].stock)

    janela._devolver_venda(venda, "segunda tentativa")

    assert int(janela.products[PRODUTO].stock) == depois_da_primeira
    gravado = janela.sale_service.get_sale(janela.session, venda)
    assert gravado["status"] == "CANCELADA"
    assert gravado["reversal_kind"] == "CANCELAMENTO"


def test_motivo_vazio_nao_reverte(janela):
    venda = _vender(janela)
    antes = int(janela.products[PRODUTO].stock)

    janela._cancelar_venda(venda, "   ")

    assert int(janela.products[PRODUTO].stock) == antes
    assert janela.sale_service.get_sale(janela.session, venda)["status"] == "CONCLUIDA"


def test_vendedor_nao_reverte(qapp, monkeypatch, tmp_path, sem_dialogos):
    window = _janela(qapp, monkeypatch, tmp_path, papel=UserRole.SELLER)
    try:
        venda = _vender(window)
        with pytest.raises(PermissionDeniedError):
            window.sale_service.cancel_sale(window.session, venda, "tentativa")
    finally:
        window.close()


def test_detalhe_abre_pela_listagem_e_volta(janela):
    venda = _vender(janela)
    janela.show_page("vendas")

    janela._show_sale_details(venda)
    assert janela.pages.currentWidget() is janela.sale_details_page
    assert janela.sale_details_page.venda["id"] == venda

    janela.sale_details_page.back_button.click()
    assert janela.pages.currentWidget() is janela.vendas_page


def test_detalhe_reflete_a_reversao_feita_nele(janela, monkeypatch):
    venda = _vender(janela)
    janela._show_sale_details(venda)
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("engano", True))
    )

    janela.sale_details_page.cancel_button.click()

    assert janela.sale_details_page.venda["status"] == "CANCELADA"
    # `isVisible()` seria False só porque a janela não está na tela;
    # `isHidden()` responde se o widget foi escondido de propósito.
    assert not janela.sale_details_page.reversao_card.isHidden()
    assert not janela.sale_details_page.cancel_button.isEnabled()


def test_reversao_atualiza_o_catalogo_que_as_outras_telas_leem(janela):
    """Estoque e Produtos compartilham o MESMO dict que a reversão altera."""
    venda = _vender(janela, quantidade=4)
    baixado = int(janela.products[PRODUTO].stock)

    janela._cancelar_venda(venda, "engano")

    assert int(janela.products[PRODUTO].stock) == baixado + 4
