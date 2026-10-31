"""Interface do comprovante (US19/SCRUM-224).

O diálogo é o ponto de entrega: mostra, grava PDF e imprime. Impressão abre
diálogo do sistema e por isso não é exercida aqui; o PDF é, porque
`QPdfWriter` funciona sem servidor gráfico.
"""

import pytest

from stockflow.application.services.receipt_renderer import (
    TITULO_CANCELADO,
    TITULO_VALIDO,
)
from stockflow.domain.sale_receipt import ReceiptCompany, build_sale_receipt
from stockflow.presentation.widgets.sale_receipt_dialog import SaleReceiptDialog

# Repetida aqui de propósito: `tests/unit` não está no caminho de import de
# `tests/` quando este arquivo roda sozinho, e `test_us17_detalhe_da_venda.py`
# já fixa a mesma convenção de venda literal no teste de tela.
EMPRESA = ReceiptCompany(name="StockFlow Comércio LTDA", document="11222333000181")

VENDA = {
    "id": "3f2a7c41-0000-4000-8000-000000000001",
    "cliente": "Ana Ferreira",
    "seller": "juliana.ramos",
    "data": "31/10/2026 14:22",
    "status": "CONCLUIDA",
    "payment_method": "PIX",
    "discount": "11.00",
    "original_total": "90.00",
    "total": "79.00",
    "valor": "R$ 79,00",
    "items": [
        {"product_code": "PRD-001", "product_name": "Teclado", "quantity": 2,
         "unit_price": "30.00", "subtotal": "60.00",
         "discount_amount": "6.00", "final_subtotal": "54.00"},
        {"product_code": "PRD-002", "product_name": "Mouse", "quantity": 1,
         "unit_price": "30.00", "subtotal": "30.00",
         "discount_amount": "0.00", "final_subtotal": "30.00"},
    ],
}

CANCELADA = VENDA | {
    "status": "CANCELADA",
    "reversal_kind": "CANCELAMENTO",
    "reversal_reason": "Registro em duplicidade",
    "reversal_on": "31/10/2026 15:00",
    "reversal_by": "ana.ferreira",
}


@pytest.fixture
def dialogo(qapp):
    janela = SaleReceiptDialog(build_sale_receipt(VENDA, EMPRESA))
    yield janela
    janela.close()


def test_dialogo_mostra_o_comprovante_renderizado(dialogo):
    texto = dialogo.viewer.toPlainText()
    assert "Ana Ferreira" in texto
    assert "Teclado" in texto
    assert "R$ 79,00" in texto
    assert TITULO_VALIDO in texto


def test_dialogo_oferece_pdf_impressao_e_fechar(dialogo):
    assert dialogo.pdf_button.isEnabled()
    assert dialogo.print_button.isEnabled()
    assert dialogo.close_button.isEnabled()


def test_nome_sugerido_carrega_o_identificador_da_venda(dialogo):
    nome = dialogo.sugerir_nome_do_arquivo()
    assert nome.endswith(".pdf")
    assert VENDA["id"][:8] in nome


def test_exportar_pdf_grava_um_arquivo_legivel(dialogo, tmp_path):
    destino = tmp_path / "comprovante.pdf"
    dialogo.export_pdf(str(destino))

    assert destino.exists()
    assert destino.read_bytes().startswith(b"%PDF")


def test_falha_na_gravacao_vira_aviso_na_janela_e_nao_derruba_o_dialogo(
    dialogo, tmp_path
):
    """Regra 7: falhar ao gerar não pode quebrar nada além da geração."""
    inexistente = tmp_path / "sem" / "pasta" / "c.pdf"
    dialogo._gravar_pdf(str(inexistente))

    assert "Não foi possível" in dialogo.status_label.text()
    assert dialogo.isEnabled()


def test_dialogo_de_venda_cancelada_mostra_a_marcacao(qapp):
    janela = SaleReceiptDialog(build_sale_receipt(CANCELADA, EMPRESA))
    try:
        texto = janela.viewer.toPlainText()
        assert TITULO_CANCELADO in texto
        assert "Registro em duplicidade" in texto
    finally:
        janela.close()


# ------------------------------------------- entrada pelo detalhe da venda

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.pages.sale_details import SaleDetailsPage


@pytest.fixture
def detalhe(qapp):
    page = SaleDetailsPage()
    yield page
    page.close()


def _vendedor():
    return conta_por_papel(UserRole.SELLER).session()


def test_detalhe_oferece_emitir_comprovante_para_venda_concluida(detalhe):
    detalhe.load_sale(VENDA, _vendedor())
    assert detalhe.receipt_button.isEnabled()


def test_detalhe_emite_o_identificador_da_venda_ao_clicar(detalhe):
    detalhe.load_sale(VENDA, _vendedor())
    pedidos = []
    detalhe.receipt_requested.connect(pedidos.append)

    detalhe.receipt_button.click()

    assert pedidos == [VENDA["id"]]


def test_detalhe_desabilita_o_botao_para_venda_pendente(detalhe):
    """Cortesia visual; a recusa de verdade é do serviço (SCRUM-227)."""
    detalhe.load_sale(VENDA | {"status": "PENDENTE"}, _vendedor())
    assert not detalhe.receipt_button.isEnabled()
    assert "não foi confirmada" in detalhe.receipt_button.toolTip()


def test_detalhe_mantem_o_botao_para_venda_cancelada(detalhe):
    """SCRUM-229: a venda cancelada tem comprovante — marcado."""
    detalhe.load_sale(CANCELADA, _vendedor())
    assert detalhe.receipt_button.isEnabled()


def test_detalhe_oferece_o_comprovante_a_quem_nao_pode_reverter(detalhe):
    """Emitir é leitura: o vendedor emite, mas não cancela nem devolve."""
    detalhe.load_sale(VENDA, _vendedor())
    assert detalhe.receipt_button.isEnabled()
    assert not detalhe.cancel_button.isVisible()


def test_detalhe_sem_venda_nao_oferece_emissao(detalhe):
    detalhe.load_sale(None, _vendedor())
    assert not detalhe.receipt_button.isEnabled()


# -------------------------------------- entrada logo após fechar a venda


def _venda_fechada(numero):
    return {
        "id": numero, "cliente": "Ana Ferreira", "produto": "Teclado",
        "valor": "R$ 79,00", "data": "31/10/2026 14:22",
        "status": "CONCLUIDA", "items": [],
    }


def test_vendas_esconde_o_botao_antes_de_qualquer_venda(vendas_page):
    assert not vendas_page.receipt_button.isVisible()


def test_vendas_oferece_comprovante_depois_de_gravar(vendas_page):
    vendas_page._venda_gravada(_venda_fechada("VND-9001"))
    pedidos = []
    vendas_page.receipt_requested.connect(pedidos.append)

    vendas_page.receipt_button.click()

    assert pedidos == ["VND-9001"]


def test_vendas_esconde_o_botao_ao_comecar_uma_venda_nova(vendas_page):
    vendas_page._venda_gravada(_venda_fechada("VND-9002"))
    vendas_page._limpar_venda()
    assert not vendas_page.receipt_button.isVisible()


def test_vendas_semente_da_demonstracao_tem_itens_para_comprovar():
    """Sem itens gravados não há comprovante, e a demonstração precisa de um
    histórico sobre o qual a US19 possa ser exercida."""
    from stockflow.infrastructure.repositories.demo_sale_repository import (
        DemoSaleRepository,
    )

    for linha in DemoSaleRepository().list_all():
        assert linha["items"]
        assert linha["status"] == "CONCLUIDA"
        assert linha["original_total"]


def test_semente_da_demonstracao_emite_comprovante_de_ponta_a_ponta():
    """A emissão sobre a semente é o caminho que o teste manual percorre."""
    from stockflow.infrastructure.repositories.demo_sale_repository import (
        DemoSaleRepository,
    )

    linha = DemoSaleRepository().list_all()[0]
    comprovante = build_sale_receipt(linha, EMPRESA)

    assert comprovante.items
    assert comprovante.net > 0


# ------------------------------------------------ ligação na janela principal


class _DialogoMudo:
    """Substitui o diálogo: estes testes são sobre não gravar, não pintar."""

    criados = []

    def __init__(self, receipt, parent=None):
        self.receipt = receipt
        _DialogoMudo.criados.append(receipt)

    def exec(self):
        return 0


@pytest.fixture
def janela(qapp):
    from stockflow.presentation.windows.main_window import MainWindow

    _DialogoMudo.criados.clear()
    window = MainWindow(conta_por_papel(UserRole.ADMIN).session())
    yield window
    window.close()


def test_janela_monta_o_servico_e_liga_as_duas_entradas(janela):
    assert janela.receipt_service is not None
    assert janela.company_repository is not None
    for pagina in (janela.sale_details_page, janela.vendas_page):
        assert pagina.receipt_requested is not None


def test_janela_abre_o_comprovante_de_uma_venda_do_historico(janela, monkeypatch):
    from stockflow.presentation.windows import main_window as modulo

    monkeypatch.setattr(modulo, "SaleReceiptDialog", _DialogoMudo)
    venda = janela.sale_repository.list_all()[0]

    janela._emitir_comprovante(venda["id"])

    assert len(_DialogoMudo.criados) == 1
    assert _DialogoMudo.criados[0].sale_id == venda["id"]


def test_janela_recusa_comprovante_de_venda_pendente_sem_abrir_dialogo(
    janela, monkeypatch
):
    """Regra 7: a recusa é uma mensagem, não uma janela de comprovante."""
    from PySide6.QtWidgets import QMessageBox
    from stockflow.presentation.windows import main_window as modulo

    monkeypatch.setattr(modulo, "SaleReceiptDialog", _DialogoMudo)
    monkeypatch.setattr(
        janela.sale_service, "get_sale",
        lambda session, sale_id: VENDA | {"status": "PENDENTE"},
    )
    avisos = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, titulo, texto, *a, **k: avisos.append(texto)),
    )

    janela._emitir_comprovante(VENDA["id"])

    assert _DialogoMudo.criados == []
    assert avisos and "não foi confirmada" in avisos[0]


def test_janela_nao_altera_venda_nem_estoque_ao_emitir(janela, monkeypatch):
    from stockflow.presentation.windows import main_window as modulo

    monkeypatch.setattr(modulo, "SaleReceiptDialog", _DialogoMudo)
    vendas_antes = [dict(linha) for linha in janela.sale_repository.list_all()]
    saldos_antes = {code: p.stock for code, p in janela.products.items()}

    janela._emitir_comprovante(vendas_antes[0]["id"])
    janela._emitir_comprovante(vendas_antes[0]["id"])

    assert [dict(l) for l in janela.sale_repository.list_all()] == vendas_antes
    assert {code: p.stock for code, p in janela.products.items()} == saldos_antes
