"""Indicadores comerciais e de estoque por período (US16).

Cálculo PURO, sobre as linhas que o repositório de vendas já devolve. Fica
no domínio pelo mesmo motivo de `replenishment.py`: a regra do que conta
como faturamento não pode morar na tela, senão o Dashboard e qualquer
relatório futuro respondem números diferentes para a mesma pergunta.

O que este módulo NÃO faz, de propósito:

- não decide quais vendas entram. O recorte de período e de situação é do
  banco (`fn_list_sales` filtra por `created_on` e por `status`), e repetir
  o filtro aqui criaria a segunda versão de uma regra que já tem dono;
- não lê preço de catálogo. O faturamento sai de `total`, que é o valor
  LÍQUIDO gravado na venda. Recalcular pelos itens reconstruiria o valor
  histórico com preço de hoje e ignoraria o desconto do cabeçalho;
- não toca saldo. A lista de estoque baixo é leitura, nunca movimentação.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from stockflow.domain.stock_level import (
    SEVERITY,
    derive_stock_status,
    is_below_minimum,
    to_int,
    to_min,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ProductRanking:
    """Um produto no ranking do período, com a quantidade comercializada."""

    code: str
    name: str
    quantity: int


@dataclass(frozen=True)
class SalesIndicators:
    """Os indicadores comerciais de UM período.

    Os quatro campos saem da MESMA leitura: separar o ranking numa segunda
    consulta permitiria que ele descrevesse um conjunto de vendas diferente
    do que produziu o faturamento exibido ao lado.
    """

    revenue: Decimal
    sales_count: int
    average_ticket: Decimal
    ranking: tuple[ProductRanking, ...]


@dataclass(frozen=True)
class LowStockProduct:
    """Produto ativo em ou abaixo do mínimo, com o saldo de AGORA."""

    code: str
    name: str
    stock: int
    minimum: int
    status: str


#: Indicadores de um período sem venda nenhuma. Existe como constante para
#: que "zerado" seja um valor, e não três literais repetidos em cada ponto
#: que precisa tratar o período vazio.
VAZIO = SalesIndicators(revenue=ZERO, sales_count=0, average_ticket=ZERO, ranking=())


def _money(valor) -> Decimal:
    """Valor comercial como `Decimal` de centavos, tolerando linha torta.

    `Decimal` e não `float`: a coluna é `numeric(10,2)` e um binário de
    ponto flutuante volta como 2499.8999999999996 — erro que só aparece
    depois de somado. Linha sem total não derruba o indicador inteiro: ela
    vale zero, que é o que uma venda sem valor gravado de fato soma.
    """
    try:
        numero = Decimal(str(valor if valor is not None else 0))
    except (InvalidOperation, ValueError):
        return ZERO
    if not numero.is_finite():
        return ZERO
    return numero.quantize(CENT, rounding=ROUND_HALF_UP)


def summarize_sales(rows) -> SalesIndicators:
    """Faturamento, quantidade, ticket médio e ranking das vendas recebidas.

    `rows` são as linhas do histórico — uma por VENDA, com os itens dentro.
    Contar linhas é o que garante que uma venda de três produtos ou com
    mais de uma forma de pagamento pese uma vez só na quantidade.

    Período sem venda devolve zero nos três indicadores, e não erro: é uma
    resposta legítima ("não vendeu nada entre essas datas"), e uma divisão
    por zero aqui transformaria essa resposta numa tela quebrada.
    """
    linhas = list(rows)
    if not linhas:
        return VAZIO

    faturamento = sum((_money(linha.get("total")) for linha in linhas), ZERO)
    quantidade = len(linhas)
    # Quantidade nunca é zero neste ponto — a lista vazia já saiu acima —,
    # mas a divisão continua protegida: o caminho de cima é o que garante
    # isso hoje, e confiar nele sem dizê-lo deixaria o próximo a mexer aqui
    # sem aviso.
    ticket = (
        (faturamento / quantidade).quantize(CENT, rounding=ROUND_HALF_UP)
        if quantidade else ZERO
    )
    return SalesIndicators(
        revenue=faturamento.quantize(CENT, rounding=ROUND_HALF_UP),
        sales_count=quantidade,
        average_ticket=ticket,
        ranking=_rank(linhas),
    )


def _rank(linhas) -> tuple[ProductRanking, ...]:
    """Produtos por quantidade vendida, do maior para o menor.

    Agrupa pelo CÓDIGO e não pelo nome: o nome do item é um snapshot da
    venda e pode ter mudado entre duas compras do mesmo produto, o que
    partiria uma linha do ranking em duas. O nome exibido é o da venda mais
    recente que trouxe aquele código.

    O desempate pelo nome não é cosmético: sem ele, dois produtos com a
    mesma quantidade trocam de lugar entre consultas e o ranking parece
    instável para quem está só atualizando a tela.
    """
    quantidades: dict[str, int] = {}
    nomes: dict[str, str] = {}
    for linha in linhas:
        for item in linha.get("items") or ():
            codigo = str(item.get("product_code") or "").strip()
            nome = str(item.get("product_name") or "").strip()
            chave = codigo or nome
            if not chave:
                continue
            quantidades[chave] = quantidades.get(chave, 0) + to_int(
                item.get("quantity"), default=0
            )
            nomes.setdefault(chave, nome or codigo)
    return tuple(
        ProductRanking(code=chave, name=nomes[chave], quantity=quantidade)
        for chave, quantidade in sorted(
            quantidades.items(),
            key=lambda par: (-par[1], nomes[par[0]].casefold(), par[0]),
        )
    )


def low_stock_products(products) -> tuple[LowStockProduct, ...]:
    """Produtos ATIVOS, com mínimo configurado, em ou abaixo dele.

    Mesmo critério da US04 — `vw_stock_alerts` no banco,
    `derive_stock_status` + `is_below_minimum` aqui. Reimplementar a
    comparação criaria a terceira versão da regra, e a primeira vez que as
    versões divergiram neste projeto a divergência passou despercebida.

    Não usa `ProductRepository.list_alerts()` porque aquele contrato
    devolve só o código, e esta lista precisa do NOME para ser legível numa
    tela de gestão.

    A situação é a de AGORA: a US16 pede o saldo atual, não a reconstrução
    histórica do estoque no fim do período consultado.
    """
    baixos = []
    for produto in products:
        if not getattr(produto, "active", True):
            continue
        minimo = to_min(getattr(produto, "minimum_stock", None))
        if minimo is None:
            continue
        situacao = derive_stock_status(produto.stock, minimo)
        if not is_below_minimum(situacao):
            continue
        baixos.append(LowStockProduct(
            code=produto.code,
            name=produto.name,
            stock=to_int(produto.stock),
            minimum=minimo,
            status=situacao,
        ))
    return tuple(sorted(
        baixos,
        key=lambda item: (SEVERITY[item.status], item.stock, item.name.casefold()),
    ))
