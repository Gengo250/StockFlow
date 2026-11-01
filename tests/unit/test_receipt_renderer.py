"""Layout do comprovante (US19/SCRUM-224).

HTML, e não CSV: o comprovante é documento de entrega ao cliente. Quem
renderiza é o `QTextBrowser`/`QTextDocument` do PySide6 já travado no
`uv.lock`, então o gerador é uma função pura e testável sem Qt.
"""

from decimal import Decimal

from stockflow.application.services.receipt_renderer import (
    AVISO_SEM_VALOR_FISCAL,
    TITULO_CANCELADO,
    TITULO_DEVOLVIDO,
    TITULO_VALIDO,
    formatar_documento,
    formatar_moeda,
    render_receipt_html,
)
from stockflow.domain.sale_receipt import ReceiptCompany, build_sale_receipt

from test_sale_receipt import EMPRESA, VENDA


def _html(venda=VENDA, empresa=EMPRESA):
    return render_receipt_html(build_sale_receipt(venda, empresa))


def test_moeda_sai_no_formato_brasileiro():
    assert formatar_moeda(Decimal("1234.5")) == "R$ 1.234,50"
    assert formatar_moeda(Decimal("0")) == "R$ 0,00"


def test_documento_completo_sai_mascarado_e_parcial_sai_cru():
    assert formatar_documento("11222333000181") == "11.222.333/0001-81"
    assert formatar_documento("52998224725") == "529.982.247-25"
    assert formatar_documento("") == ""
    assert formatar_documento("123") == "123"


def test_cabecalho_traz_empresa_e_titulo_de_comprovante_valido():
    html = _html()
    assert "StockFlow Comércio LTDA" in html
    assert "11.222.333/0001-81" in html
    assert TITULO_VALIDO in html
    assert TITULO_CANCELADO not in html


def test_corpo_traz_identificador_data_cliente_responsavel_e_pagamento():
    html = _html()
    assert VENDA["id"] in html
    assert "31/10/2026 14:22" in html
    assert "Ana Ferreira" in html
    assert "juliana.ramos" in html
    assert "PIX" in html


def test_itens_saem_com_quantidade_preco_desconto_e_subtotal():
    html = _html()
    assert "PRD-001" in html and "Teclado" in html
    assert "R$ 30,00" in html
    assert "R$ 60,00" in html
    assert "R$ 6,00" in html
    assert "R$ 54,00" in html


def test_totais_mostram_bruto_descontos_e_total_final():
    html = _html()
    assert "R$ 90,00" in html
    assert "R$ 11,00" in html
    assert "R$ 79,00" in html


def test_venda_sem_cliente_nao_imprime_rotulo_de_cliente_vazio():
    html = _html(VENDA | {"cliente": ""})
    assert "Cliente" not in html


def test_comprovante_de_venda_cancelada_grita_o_cancelamento():
    cancelada = VENDA | {
        "status": "CANCELADA",
        "reversal_kind": "CANCELAMENTO",
        "reversal_reason": "Registro em duplicidade",
        "reversal_on": "31/10/2026 15:00",
        "reversal_by": "ana.ferreira",
    }
    html = _html(cancelada)

    assert TITULO_CANCELADO in html
    assert TITULO_VALIDO not in html
    assert "Registro em duplicidade" in html
    assert "ana.ferreira" in html
    # Os dados comerciais originais continuam lá.
    assert "R$ 79,00" in html
    assert "Teclado" in html


def test_titulos_sao_disjuntos_para_que_um_nao_valha_pelo_outro():
    """Se o título de cancelada contivesse o de válida, "diferenciar os dois"
    (SCRUM-229) passaria no teste sem ser verdade na tela."""
    assert TITULO_VALIDO not in TITULO_CANCELADO
    assert TITULO_VALIDO not in TITULO_DEVOLVIDO


def test_comprovante_de_venda_devolvida_usa_o_titulo_da_devolucao():
    devolvida = VENDA | {
        "status": "DEVOLVIDA",
        "reversal_kind": "DEVOLUCAO",
        "reversal_reason": "Cliente desistiu",
        "reversal_on": "31/10/2026 16:00",
        "reversal_by": "ana.ferreira",
    }
    html = _html(devolvida)

    assert TITULO_DEVOLVIDO in html
    assert TITULO_VALIDO not in html
    assert "Devolução" in html


def test_empresa_sem_cadastro_nao_imprime_cabecalho_fantasma():
    html = _html(empresa=ReceiptCompany(name="", document=""))
    assert TITULO_VALIDO in html
    assert "CNPJ" not in html


def test_comprovante_avisa_que_nao_tem_valor_fiscal():
    """Não é nota fiscal, e o documento precisa dizer isso."""
    assert AVISO_SEM_VALOR_FISCAL in _html()


def test_conteudo_do_cliente_e_escapado_e_nao_vira_marcacao():
    html = _html(VENDA | {"cliente": "Casa & Cia <b>"})
    assert "Casa &amp; Cia &lt;b&gt;" in html
