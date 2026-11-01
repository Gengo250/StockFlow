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

_BORDA = "#E2E8F0"
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


def _linha(rotulo, valor):
    return (f"<tr><td style='color:{_SUAVE};padding:2px 12px 2px 0'>{rotulo}</td>"
            f"<td style='color:{_TEXTO}'>{valor}</td></tr>")


def _cabecalho_da_empresa(receipt):
    if not receipt.company.identificada:
        # Sem cadastro legível não se inventa emitente: um cabeçalho em
        # branco diria que a empresa se chama "".
        return ""
    documento = formatar_documento(receipt.company.document)
    linha_documento = (
        f"<div style='color:{_SUAVE};font-size:11px'>CNPJ {escape(documento)}</div>"
        if documento else ""
    )
    return (f"<div style='font-size:16px;font-weight:bold;color:{_TEXTO}'>"
            f"{escape(receipt.company.name)}</div>{linha_documento}")


def _titulo(receipt):
    if not receipt.cancelado:
        return (f"<div style='font-size:14px;font-weight:bold;color:{_TEXTO};"
                f"padding:10px 0'>{TITULO_VALIDO}</div>")
    rotulo = TITULO_DE_REVERSAO[receipt.status]
    return (f"<div style='font-size:14px;font-weight:bold;color:{_ALERTA};"
            f"border:2px solid {_ALERTA};padding:8px'>{rotulo}</div>")


def _dados_da_operacao(receipt):
    linhas = [_linha("Venda", escape(receipt.sale_id)),
              _linha("Data", escape(receipt.issued_on))]
    # Cliente só aparece quando a venda tem um associado (regra 3).
    if receipt.client:
        linhas.append(_linha("Cliente", escape(receipt.client)))
    linhas.append(_linha("Responsável", escape(receipt.seller or "—")))
    return "<table>" + "".join(linhas) + "</table>"


def _itens(receipt):
    cabecalho = "".join(
        f"<th align='{alinhamento}' style='border-bottom:1px solid {_BORDA};"
        f"color:{_SUAVE};font-weight:normal'>{titulo}</th>"
        for titulo, alinhamento in (
            ("Código", "left"), ("Produto", "left"), ("Qtd.", "right"),
            ("Preço unit.", "right"), ("Subtotal", "right"),
            ("Desconto", "right"), ("Total", "right"),
        )
    )
    corpo = "".join(
        "<tr>"
        f"<td>{escape(item.code)}</td>"
        f"<td>{escape(item.name)}</td>"
        f"<td align='right'>{item.quantity}</td>"
        f"<td align='right'>{formatar_moeda(item.unit_price)}</td>"
        f"<td align='right'>{formatar_moeda(item.subtotal)}</td>"
        f"<td align='right'>{formatar_moeda(item.discount)}</td>"
        f"<td align='right'>{formatar_moeda(item.final_subtotal)}</td>"
        "</tr>"
        for item in receipt.items
    )
    return (f"<table width='100%' cellpadding='4' cellspacing='0'>"
            f"<tr>{cabecalho}</tr>{corpo}</table>")


def _totais(receipt):
    linhas = [_linha("Subtotal bruto", formatar_moeda(receipt.gross))]
    # Os dois escopos de desconto (US22) só aparecem quando existem: linha
    # zerada ocupa espaço do papel afirmando que não houve desconto duas
    # vezes, e o total consolidado logo abaixo já diz isso.
    if receipt.item_discount:
        linhas.append(_linha("Descontos nos itens",
                             formatar_moeda(receipt.item_discount)))
    if receipt.sale_discount:
        linhas.append(_linha("Desconto na venda",
                             formatar_moeda(receipt.sale_discount)))
    linhas.append(_linha("Desconto total", formatar_moeda(receipt.total_discount)))
    linhas.append(
        f"<tr><td style='font-size:14px;font-weight:bold;padding-top:6px'>TOTAL</td>"
        f"<td style='font-size:14px;font-weight:bold;padding-top:6px'>"
        f"{formatar_moeda(receipt.net)}</td></tr>"
    )
    return "<table>" + "".join(linhas) + "</table>"


def _pagamento(receipt):
    return ("<table>"
            + _linha("Forma de pagamento", escape(receipt.payment.method or "—"))
            + _linha("Valor pago", formatar_moeda(receipt.payment.amount))
            + "</table>")


def _cancelamento(receipt):
    reversao = receipt.cancellation
    if reversao is None:
        return ""
    return (f"<table style='color:{_ALERTA}'>"
            + _linha("Operação", escape(reversao.kind.label))
            + _linha("Motivo", escape(reversao.reason or "—"))
            + _linha("Quando", escape(reversao.when or "—"))
            + _linha("Responsável", escape(reversao.by or "—"))
            + "</table>")


def render_receipt_html(receipt: SaleReceipt) -> str:
    """Documento completo, pronto para `QTextDocument.setHtml`."""
    separador = f"<hr style='border:0;border-top:1px solid {_BORDA}'>"
    return (
        f"<div style='font-family:sans-serif;font-size:12px;color:{_TEXTO}'>"
        f"{_cabecalho_da_empresa(receipt)}"
        f"{_titulo(receipt)}"
        f"{_dados_da_operacao(receipt)}{separador}"
        f"{_itens(receipt)}{separador}"
        f"{_totais(receipt)}{separador}"
        f"{_pagamento(receipt)}"
        f"{_cancelamento(receipt)}"
        f"<div style='color:{_SUAVE};font-size:10px;padding-top:12px'>"
        f"{AVISO_SEM_VALOR_FISCAL}</div>"
        f"</div>"
    )
