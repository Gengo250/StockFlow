"""Comprovante de venda (US19/SCRUM-213).

O comprovante é LEITURA do que foi gravado, nunca registro novo. Reemitir
relê `sales`/`sale_items`, onde o nome do cliente e o nome, código e preço do
produto já são congelados na gravação (`database/code/tables/06_clients_sales.sql`).
É esse snapshot — e não uma cópia feita aqui — que faz um cadastro editado
depois não reescrever um documento histórico.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from stockflow.domain.enums.sale_reversal_kind import SaleReversalKind
from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.domain.sale_discount import calculate_discount_breakdown

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

SEM_VENDA = "Esta venda não está mais disponível para esta empresa."
NAO_CONFIRMADA = (
    "Esta venda ainda não foi confirmada. Finalize a venda antes de emitir "
    "o comprovante."
)
SEM_ITENS = "Esta venda não tem itens gravados e não pode gerar comprovante."
DADOS_INCONSISTENTES = (
    "Os valores gravados nesta venda não fecham, e o comprovante não pode "
    "ser emitido com números que não conferem."
)


class ReceiptNotAvailable(ValueError):
    """A venda não pode gerar comprovante definitivo.

    `ValueError` e não exceção de raiz própria: a tela já trata `ValueError`
    como recusa de domínio em todo o fluxo de vendas, e um tipo fora dessa
    hierarquia faria o tratamento existente deixar passar justamente a
    recusa desta história.
    """


@dataclass(frozen=True)
class ReceiptCompany:
    """Emitente. Vem do cadastro ATUAL, não do snapshot da venda.

    Diferente do cliente de propósito: a empresa é quem emite o documento,
    não uma grandeza comercial da operação.
    """

    name: str
    document: str = ""

    @property
    def identificada(self) -> bool:
        return bool(self.name.strip())


@dataclass(frozen=True)
class ReceiptItem:
    code: str
    name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    discount: Decimal
    final_subtotal: Decimal


@dataclass(frozen=True)
class ReceiptPayment:
    method: str
    amount: Decimal


@dataclass(frozen=True)
class ReceiptCancellation:
    kind: SaleReversalKind
    reason: str
    when: str
    by: str


@dataclass(frozen=True)
class SaleReceipt:
    sale_id: str
    issued_on: str
    company: ReceiptCompany
    #: `None` quando a venda não tem cliente associado (regra 3). Vazio não
    #: serve: a tela precisa distinguir "sem cliente" de "nome em branco".
    client: str | None
    seller: str
    status: SaleStatus
    items: tuple[ReceiptItem, ...]
    payment: ReceiptPayment
    gross: Decimal
    item_discount: Decimal
    sale_discount: Decimal
    total_discount: Decimal
    net: Decimal
    cancellation: ReceiptCancellation | None = None

    @property
    def cancelado(self) -> bool:
        return self.status.revertida


def _dinheiro(valor) -> Decimal:
    if valor is None or valor == "":
        return ZERO
    try:
        quantia = Decimal(str(valor))
    except (ArithmeticError, InvalidOperation, TypeError, ValueError) as erro:
        raise ReceiptNotAvailable(DADOS_INCONSISTENTES) from erro
    if not quantia.is_finite():
        raise ReceiptNotAvailable(DADOS_INCONSISTENTES)
    return quantia.quantize(CENT, rounding=ROUND_HALF_UP)


def _quantidade(valor) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError) as erro:
        raise ReceiptNotAvailable(DADOS_INCONSISTENTES) from erro


def _item(linha) -> ReceiptItem:
    subtotal = _dinheiro(linha.get("subtotal"))
    desconto = _dinheiro(linha.get("discount_amount"))
    return ReceiptItem(
        code=str(linha.get("product_code") or ""),
        name=str(linha.get("product_name") or ""),
        quantity=_quantidade(linha.get("quantity") or 0),
        unit_price=_dinheiro(linha.get("unit_price")),
        subtotal=subtotal,
        discount=desconto,
        # `final_subtotal` é coluna gerada no banco; o fallback cobre a linha
        # que chega do recibo da gravação, que não a traz.
        final_subtotal=_dinheiro(linha.get("final_subtotal", subtotal - desconto)),
    )


def _cancelamento(venda) -> ReceiptCancellation | None:
    especie = venda.get("reversal_kind")
    if not especie:
        return None
    return ReceiptCancellation(
        kind=SaleReversalKind.from_value(especie),
        reason=str(venda.get("reversal_reason") or ""),
        when=str(venda.get("reversal_on") or ""),
        by=str(venda.get("reversal_by") or ""),
    )


def build_sale_receipt(venda, company: ReceiptCompany) -> SaleReceipt:
    """Monta o comprovante a partir do retorno de `SaleService.get_sale`.

    A regra de status mora AQUI e em nenhum outro lugar: a tela desabilita o
    botão por cortesia, mas quem recusa é esta função — senão a recusa teria
    duas redações e uma delas ficaria para trás.
    """
    if not venda:
        raise ReceiptNotAvailable(SEM_VENDA)

    status = SaleStatus.from_value(venda.get("status") or SaleStatus.CONCLUIDA)
    if status is SaleStatus.PENDENTE:
        raise ReceiptNotAvailable(NAO_CONFIRMADA)

    itens = tuple(_item(linha) for linha in (venda.get("items") or ()))
    if not itens:
        raise ReceiptNotAvailable(SEM_ITENS)

    bruto = _dinheiro(venda.get("original_total", venda.get("total")))
    descontos_de_item = tuple(item.discount for item in itens)
    desconto_total = _dinheiro(venda.get("discount"))
    desconto_da_venda = desconto_total - sum(descontos_de_item, start=ZERO)
    try:
        # Reusa a aritmética que a US22 já valida. Uma segunda redação da
        # mesma conta divergiria no primeiro arredondamento.
        resumo = calculate_discount_breakdown(
            bruto, descontos_de_item, desconto_da_venda
        )
    except ValueError as erro:
        raise ReceiptNotAvailable(DADOS_INCONSISTENTES) from erro

    cliente = str(venda.get("cliente") or "").strip()
    return SaleReceipt(
        sale_id=str(venda.get("id") or ""),
        issued_on=str(venda.get("data") or ""),
        company=company,
        client=cliente or None,
        seller=str(venda.get("seller") or "").strip(),
        status=status,
        items=itens,
        payment=ReceiptPayment(
            method=str(venda.get("payment_method") or ""),
            amount=_dinheiro(venda.get("total")),
        ),
        gross=resumo.gross,
        item_discount=resumo.item_discount,
        sale_discount=resumo.sale_discount,
        total_discount=resumo.total_discount,
        net=resumo.net,
        cancellation=_cancelamento(venda),
    )
