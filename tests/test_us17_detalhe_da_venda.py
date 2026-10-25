"""Tela de detalhe da venda (US17/SCRUM-221).

O critério de aceite exige itens, quantidades, preços, descontos, totais,
pagamento, cliente e responsável. Até a US17 o único "detalhe" era um
tooltip com nome e quantidade.
"""

import pytest
from PySide6.QtWidgets import QAbstractItemView

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.pages.sale_details import SaleDetailsPage

VENDA = {
    "id": "VND-0001",
    "cliente": "Ana Ferreira",
    "seller": "João Vendedor",
    "data": "05/10/2026 14:30",
    "status": "CONCLUIDA",
    "payment_method": "PIX",
    "discount": "5.00",
    "total": "115.00",
    "valor": "R$ 115,00",
    "items": [
        {"product_code": "PRD-001", "product_name": "Teclado",
         "quantity": 2, "unit_price": "30.00", "subtotal": "60.00"},
        {"product_code": "PRD-002", "product_name": "Mouse",
         "quantity": 2, "unit_price": "30.00", "subtotal": "60.00"},
    ],
}

REVERTIDA = VENDA | {
    "status": "DEVOLVIDA",
    "reversal_kind": "DEVOLUCAO",
    "reversal_reason": "Cliente desistiu da compra",
    "reversal_on": "06/10/2026 09:00",
    "reversal_by": "Maria Admin",
}

CANCELADA = VENDA | {
    "status": "CANCELADA",
    "reversal_kind": "CANCELAMENTO",
    "reversal_reason": "Registro em duplicidade",
    "reversal_on": "05/10/2026 15:00",
    "reversal_by": "Maria Admin",
}


@pytest.fixture
def pagina(qapp):
    page = SaleDetailsPage()
    yield page
    page.close()


def admin():
    return conta_por_papel(UserRole.ADMIN).session()


# ------------------------------------------------------ o que o detalhe mostra


def test_detalhe_mostra_cliente_vendedor_e_pagamento(pagina):
    pagina.load_sale(VENDA, admin())
    texto = pagina.resumo_text()
    assert "Ana Ferreira" in texto
    assert "João Vendedor" in texto
    assert "PIX" in texto
    assert "VND-0001" in texto


def test_detalhe_lista_itens_com_preco_unitario_e_subtotal(pagina):
    pagina.load_sale(VENDA, admin())
    assert pagina.itens_table.rowCount() == 2
    cabecalhos = [
        pagina.itens_table.horizontalHeaderItem(c).text()
        for c in range(pagina.itens_table.columnCount())
    ]
    assert "Preço unitário" in cabecalhos
    assert "Subtotal" in cabecalhos
    assert pagina.itens_table.item(0, 0).text() == "PRD-001"
    assert pagina.itens_table.item(0, 3).text() == "R$ 30,00"
    assert pagina.itens_table.item(0, 4).text() == "R$ 60,00"


def test_detalhe_mostra_bruto_desconto_e_total(pagina):
    pagina.load_sale(VENDA, admin())
    texto = pagina.totais_label.text()
    assert "R$ 120,00" in texto
    assert "R$ 5,00" in texto
    assert "R$ 115,00" in texto


def test_item_sem_preco_mostra_travessao_e_nao_zero():
    """Zero seria uma afirmação falsa sobre o preço que não veio."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    page = SaleDetailsPage()
    try:
        page.load_sale(
            VENDA | {"items": [{"product_code": "P1", "product_name": "X",
                                "quantity": 1}]},
            admin(),
        )
        assert page.itens_table.item(0, 3).text() == "—"
        assert page.itens_table.item(0, 4).text() == "—"
    finally:
        page.close()


def test_venda_sem_detalhe_mostra_aviso_em_vez_de_tela_vazia(pagina):
    pagina.load_sale(None, admin())
    assert not pagina.error_label.isHidden()
    assert pagina.itens_table.rowCount() == 0


# ------------------------------------------- SCRUM-222: vínculo de reversão


def test_venda_devolvida_mostra_motivo_autor_e_data(pagina):
    pagina.load_sale(REVERTIDA, admin())
    assert not pagina.reversao_card.isHidden()
    texto = pagina.reversao_label.text()
    assert "Devolução" in texto
    assert "Cliente desistiu da compra" in texto
    assert "Maria Admin" in texto
    assert "06/10/2026" in texto


def test_venda_cancelada_distingue_a_especie(pagina):
    pagina.load_sale(CANCELADA, admin())
    assert "Cancelamento" in pagina.reversao_label.text()
    assert "Registro em duplicidade" in pagina.reversao_label.text()


def test_venda_sem_reversao_esconde_o_bloco(pagina):
    pagina.load_sale(VENDA, admin())
    # `isHidden()`, e não `isVisible()`: este último seria False de qualquer
    # jeito numa janela que não foi mostrada, e o teste passaria sem provar
    # nada.
    assert pagina.reversao_card.isHidden()


def test_status_aparece_no_resumo(pagina):
    pagina.load_sale(REVERTIDA, admin())
    assert pagina.status_label.text() == "Devolvida"


# --------------------------------------------------- SCRUM-223: alçada e edição


def test_admin_ve_as_acoes_em_venda_concluida(pagina):
    pagina.load_sale(VENDA, admin())
    assert pagina.cancel_button.isEnabled()
    assert pagina.return_button.isEnabled()


@pytest.mark.parametrize("papel", [UserRole.SELLER, UserRole.STOCK])
def test_quem_nao_e_admin_nao_reverte(pagina, papel):
    pagina.load_sale(VENDA, conta_por_papel(papel).session())
    assert not pagina.cancel_button.isEnabled()
    assert not pagina.return_button.isEnabled()


def test_sessao_ausente_nao_reverte(pagina):
    pagina.load_sale(VENDA, None)
    assert not pagina.cancel_button.isEnabled()
    assert not pagina.return_button.isEnabled()


@pytest.mark.parametrize("venda", [REVERTIDA, CANCELADA])
def test_venda_ja_revertida_nao_oferece_acao_nem_para_admin(pagina, venda):
    pagina.load_sale(venda, admin())
    assert not pagina.cancel_button.isEnabled()
    assert not pagina.return_button.isEnabled()


def test_detalhe_nao_permite_editar_os_itens(pagina):
    pagina.load_sale(VENDA, admin())
    assert pagina.itens_table.editTriggers() == QAbstractItemView.NoEditTriggers


# ------------------------------------------------------- motivo obrigatório


def test_cancelar_sem_motivo_nao_emite_nada(pagina, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("   ", True)))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    pedidos = []
    pagina.cancel_requested.connect(lambda *args: pedidos.append(args))
    pagina.load_sale(VENDA, admin())
    pagina.cancel_button.click()
    assert pedidos == []


def test_cancelar_cancelado_pelo_usuario_nao_emite_nada(pagina, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("engano", False)))
    pedidos = []
    pagina.cancel_requested.connect(lambda *args: pedidos.append(args))
    pagina.load_sale(VENDA, admin())
    pagina.cancel_button.click()
    assert pedidos == []


def test_cancelar_com_motivo_emite_id_e_motivo(pagina, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("  engano  ", True)))
    pedidos = []
    pagina.cancel_requested.connect(lambda *args: pedidos.append(args))
    pagina.load_sale(VENDA, admin())
    pagina.cancel_button.click()
    assert pedidos == [("VND-0001", "engano")]


def test_devolver_com_motivo_emite_id_e_motivo(pagina, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("defeito", True)))
    pedidos = []
    pagina.return_requested.connect(lambda *args: pedidos.append(args))
    pagina.load_sale(VENDA, admin())
    pagina.return_button.click()
    assert pedidos == [("VND-0001", "defeito")]


def test_motivo_longo_demais_e_recusado_na_tela(pagina, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("x" * 301, True)))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    pedidos = []
    pagina.cancel_requested.connect(lambda *args: pedidos.append(args))
    pagina.load_sale(VENDA, admin())
    pagina.cancel_button.click()
    assert pedidos == []
