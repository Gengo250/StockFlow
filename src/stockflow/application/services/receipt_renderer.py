"""Layout do comprovante de venda em HTML (US19/SCRUM-224).

Função pura, na mesma camada e pelo mesmo motivo que `csv_exporter.py`:
serializar documento é caso de uso, não desenho de tela. Quem pinta é o
`QTextDocument`, que aceita um subconjunto de HTML 4 — por isso tabela com
`cellpadding` e estilo em atributo, e nada de CSS moderno.
"""

from decimal import Decimal
from html import escape

from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.domain.sale_receipt import SaleReceipt

TITULO_VALIDO = "COMPROVANTE DE VENDA"
# Disjuntos do título válido de propósito. Se um fosse prefixo do outro,
# "diferenciar comprovante cancelado de válido" (SCRUM-229) viraria uma
# afirmação que passa no teste e falha na leitura de quem recebe o papel.
TITULO_CANCELADO = "VENDA CANCELADA · COMPROVANTE SEM VALIDADE"
TITULO_DEVOLVIDO = "VENDA DEVOLVIDA · COMPROVANTE SEM VALIDADE"

AVISO_SEM_VALOR_FISCAL = (
    "Documento de conferência emitido pelo StockFlow. Não tem valor fiscal."
)

TITULO_DE_REVERSAO = {
    SaleStatus.CANCELADA: TITULO_CANCELADO,
    SaleStatus.DEVOLVIDA: TITULO_DEVOLVIDO,
}

_TEXTO = "#0F172A"
_SUAVE = "#64748B"
_ALERTA = "#B91C1C"


def formatar_moeda(valor: Decimal) -> str:
    """`Decimal("1234.5")` -> `"R$ 1.234,50"`."""
    texto = f"{Decimal(valor):,.2f}".replace(",", "_").replace(".", ",")
    return "R$ " + texto.replace("_", ".")


def formatar_documento(documento: str) -> str:
    """Mascara CPF/CNPJ completo; devolve cru o que não tiver o tamanho."""
    digitos = "".join(c for c in (documento or "") if c.isdigit())
    if len(digitos) == 14:
        return (f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}"
                f"/{digitos[8:12]}-{digitos[12:]}")
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return documento or ""


def _linha(rotulo, valor, alinhamento='left'):
    return (f"<tr><td valign='top' style='color:{_SUAVE}'>{rotulo}</td>"
            f"<td valign='top' align='{alinhamento}' style='color:{_TEXTO}'>{valor}</td></tr>")


def _cabecalho_da_empresa(receipt):
    if not receipt.company.identificada:
        # Sem cadastro legível não se inventa emitente: um cabeçalho em
        # branco diria que a empresa se chama "".
        return ""
    documento = formatar_documento(receipt.company.document)
    linha_documento = (
        f"<p style='color:{_SUAVE};font-size:10pt;margin-top:4px;margin-bottom:16px'>"
        f"CNPJ {escape(documento)}</p>"
        if documento else ""
    )
    return (f"<p style='font-size:18pt;font-weight:bold;color:{_TEXTO};margin:0'>"
            f"{escape(receipt.company.name)}</p>{linha_documento}")


def _titulo(receipt):
    if not receipt.cancelado:
        return (f"<p style='font-size:16pt;font-weight:bold;color:{_TEXTO};"
                f"margin-top:16px;margin-bottom:14px'>{TITULO_VALIDO}</p>")
    rotulo = TITULO_DE_REVERSAO[receipt.status]
    return (f"<p style='font-size:16pt;font-weight:bold;color:{_ALERTA};"
            f"margin-top:16px;margin-bottom:14px'>{rotulo}</p>")


def _dados_da_operacao(receipt):
    linhas = [_linha("Venda", escape(receipt.sale_id)),
              _linha("Data", escape(receipt.issued_on))]
    # Cliente só aparece quando a venda tem um associado (regra 3).
    if receipt.client:
        linhas.append(_linha("Cliente", escape(receipt.client)))
    linhas.append(_linha("Responsável", escape(receipt.seller or "—")))
    return "<table cellpadding='5' cellspacing='0'>" + "".join(linhas) + "</table>"


def _itens(receipt):
    cabecalho = "".join(
        f"<th width='{largura}' align='{alinhamento}' valign='top' "
        f"bgcolor='#F1F5F9' style='color:{_TEXTO};font-weight:bold'>{titulo}</th>"
        for titulo, largura, alinhamento in (
            ("Produto / código", "27%", "left"), ("Qtd.", "10%", "right"),
            ("Preço unit.", "21%", "right"),
            ("Desconto", "21%", "right"), ("Total", "21%", "right"),
        )
    )
    corpo = "".join(
        f"<tr bgcolor='{'#FFFFFF' if index % 2 else '#F8FAFC'}'>"
        f"<td valign='top'><b>{escape(item.name)}</b><br>"
        f"<span style='font-size:10pt;color:{_SUAVE}'>{escape(item.code)}<br>"
        f"Subtotal bruto: {formatar_moeda(item.subtotal)}</span></td>"
        f"<td valign='top' align='right'>{item.quantity}</td>"
        f"<td valign='top' align='right'>{formatar_moeda(item.unit_price)}</td>"
        f"<td valign='top' align='right'>{formatar_moeda(item.discount)}</td>"
        f"<td valign='top' align='right'>{formatar_moeda(item.final_subtotal)}</td>"
        "</tr>"
        for index, item in enumerate(receipt.items)
    )
    return (f"<table width='100%' cellpadding='8' cellspacing='0'>"
            f"<thead><tr>{cabecalho}</tr></thead>{corpo}</table>")


def _totais(receipt):
    linhas = [_linha("Subtotal bruto", formatar_moeda(receipt.gross), 'right')]
    # Os dois escopos de desconto (US22) só aparecem quando existem: linha
    # zerada ocupa espaço do papel afirmando que não houve desconto duas
    # vezes, e o total consolidado logo abaixo já diz isso.
    if receipt.item_discount:
        linhas.append(_linha("Descontos nos itens",
                             formatar_moeda(receipt.item_discount), 'right'))
    if receipt.sale_discount:
        linhas.append(_linha("Desconto na venda",
                             formatar_moeda(receipt.sale_discount), 'right'))
    linhas.append(_linha("Desconto total", formatar_moeda(receipt.total_discount), 'right'))
    linhas.append(
        f"<tr bgcolor='#EFF6FF'><td style='font-size:15pt;font-weight:bold'>TOTAL</td>"
        f"<td align='right' style='font-size:15pt;font-weight:bold'>"
        f"{formatar_moeda(receipt.net)}</td></tr>"
    )
    return "<table width='100%' cellpadding='6' cellspacing='0'>" + "".join(linhas) + "</table>"


def _pagamento(receipt):
    return ("<table cellpadding='5' cellspacing='0'>"
            + _linha("Forma de pagamento", escape(receipt.payment.method or "—"))
            + _linha("Valor pago", formatar_moeda(receipt.payment.amount))
            + "</table>")


def _cancelamento(receipt):
    reversao = receipt.cancellation
    if reversao is None:
        return ""
    return (f"<table cellpadding='5' cellspacing='0' style='color:{_ALERTA}'>"
            + _linha("Operação", escape(reversao.kind.label))
            + _linha("Motivo", escape(reversao.reason or "—"))
            + _linha("Quando", escape(reversao.when or "—"))
            + _linha("Responsável", escape(reversao.by or "—"))
            + "</table>")


def render_receipt_html(receipt: SaleReceipt) -> str:
    """Documento completo, pronto para `QTextDocument.setHtml`."""
    def secao(titulo):
        return (f"<p style='font-size:12pt;font-weight:bold;margin-top:18px;"
                f"margin-bottom:8px'>{titulo}</p>")

    return (
        f"<html><body style='font-family:sans-serif;font-size:11pt;color:{_TEXTO};"
        f"background-color:#FFFFFF'>"
        f"{_cabecalho_da_empresa(receipt)}"
        f"{_titulo(receipt)}"
        f"{_dados_da_operacao(receipt)}"
        f"{secao('Itens da venda')}{_itens(receipt)}"
        f"{secao('Resumo')}{_totais(receipt)}"
        f"{secao('Pagamento')}{_pagamento(receipt)}"
        f"{_cancelamento(receipt)}"
        f"<p style='color:{_SUAVE};font-size:10pt;margin-top:20px;line-height:130%'>"
        f"{AVISO_SEM_VALOR_FISCAL}</p>"
        f"</body></html>"
    )
