"""Tradução entre a linha de `public.products` e o `Product` do catálogo.

As duas pontas falam formatos diferentes, e a diferença não é cosmética:

| catálogo (UI)        | banco                                |
|----------------------|--------------------------------------|
| `code` `"PRD-009"`   | `barcode text` UNIQUE (company_id,…) |
| `"R$ 2.499,90"`      | `sell_price numeric(10,2)`           |
| `"Unidade (UN)"`     | `unit public.unit_enum` = `'UN'`     |
| `category` por nome  | `item_category uuid` (FK composta)   |
| `stock` `"18"`       | `stock integer`                      |
| `minimum_stock` int? | `product_stock.min_quantity` (nullable) |

O `code` vira `barcode` porque é a única coluna com unicidade por empresa que
carrega um identificador de negócio: `products.id` é um uuid gerado pelo banco
e não existe antes do INSERT, então não serve para a tela, que precisa exibir
e procurar o produto pelo código. A consequência a lembrar é que o uuid é a
identidade REAL — `fn_update_products` e `fn_set_product_active` recebem
`p_product_id`, e por isso toda escrita resolve `barcode -> id` antes.
"""

from decimal import Decimal, InvalidOperation

from stockflow.domain.enums.product_unit import PRODUCT_UNITS
from stockflow.domain.stock_level import (
    derive_stock_status,
    to_int,
    to_min,
)
from stockflow.presentation.demo_products import Product

# "Unidade (UN)" <-> "UN". Derivado de PRODUCT_UNITS em vez de escrito à mão:
# a lista da UI já declara o código do enum entre parênteses, e manter um
# segundo dicionário literal deixaria os dois dessincronizados na primeira
# unidade nova.
UNIT_BY_LABEL = {label: label.rsplit("(", 1)[1].rstrip(")") for label in PRODUCT_UNITS}
LABEL_BY_UNIT = {code: label for label, code in UNIT_BY_LABEL.items()}

DEFAULT_UNIT = "UN"


def unit_to_db(label) -> str:
    """Rótulo da tela para o valor de `public.unit_enum`.

    Aceita o próprio código ("UN") além do rótulo, porque um `Product` lido do
    banco e reenviado sem passar pela tela já carrega o código.
    """
    texto = (label or "").strip()
    if texto in UNIT_BY_LABEL:
        return UNIT_BY_LABEL[texto]
    if texto in LABEL_BY_UNIT:
        return texto
    return DEFAULT_UNIT


def unit_to_label(unit) -> str:
    """Valor do enum para o rótulo que o formulário mostra."""
    texto = (unit or "").strip()
    return LABEL_BY_UNIT.get(texto, texto or LABEL_BY_UNIT[DEFAULT_UNIT])


def money_to_db(texto) -> Decimal:
    """"R$ 2.499,90" -> Decimal("2499.90").

    `Decimal`, e não `float`: a coluna é `numeric(10,2)` e um binário de
    ponto flutuante chega lá como 2499.8999999999996 — erro que aparece na
    soma de uma venda, não no cadastro.
    """
    if texto is None:
        return Decimal("0")
    limpo = str(texto).replace("R$", "").strip().replace(" ", "")
    # Formato brasileiro só quando há vírgula decimal; "2499.90" vindo de uma
    # chamada não-UI continua válido.
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo or "0")
    except InvalidOperation:
        return Decimal("0")


def money_to_label(valor) -> str:
    """Decimal/str do banco -> "R$ 2.499,90", o formato que o catálogo guarda."""
    if valor is None:
        valor = 0
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        numero = Decimal("0")
    bruto = f"{numero:,.2f}"
    return "R$ " + bruto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def row_to_product(row, category_name=None, minimum_stock=None) -> Product:
    """Linha de `products` (+ nome da categoria e mínimo) para `Product`.

    `category_name` e `minimum_stock` chegam de fora porque moram em outras
    tabelas (`categories` e `product_stock`). Resolver cada um com uma consulta
    por produto daria N+1; quem chama resolve em lote e passa pronto.

    O `stock_status` é DERIVADO aqui, nunca lido: o banco não guarda o rótulo
    (a view `vw_stock_situation` também o calcula), e inventar um campo
    persistido criaria uma segunda verdade sobre a mesma coisa.
    """
    # Ausente PERMANECE ausente. `product_stock.min_quantity` é nullable, e
    # produto sem linha também chega como `None` — os dois casos significam
    # "sem limiar" e não podem virar zero, que agora é uma configuração que
    # alerta ao zerar o saldo.
    minimo = to_min(minimum_stock)
    estoque = to_int(row.get("stock"))
    return Product(
        code=row.get("barcode") or "",
        name=row.get("name") or "",
        category=category_name or "",
        unit=unit_to_label(row.get("unit")),
        sale_price=money_to_label(row.get("sell_price")),
        cost=money_to_label(row.get("buy_price")),
        active=bool(row.get("active", True)),
        stock=str(estoque),
        stock_status=derive_stock_status(estoque, minimo),
        minimum_stock=minimo,
    )


def product_input_to_create_args(data, company_id) -> dict:
    """Argumentos nomeados de `fn_create_products`.

    `p_item_category` vai como NOME, não uuid: a função resolve o id dentro da
    empresa dela própria e levanta 'Item category doesnt exist' quando não
    acha. Mandar uuid daqui obrigaria o cliente a consultar `categories`
    antes e abriria espaço para apontar categoria de outra empresa.
    """
    return {
        "p_company_id": company_id,
        "p_barcode": data.code,
        "p_name": data.name,
        "p_sell_price": str(money_to_db(data.sale_price)),
        "p_buy_price": str(money_to_db(data.cost)),
        "p_unit": unit_to_db(data.unit),
        "p_stock": to_int(data.stock),
        "p_item_category": data.category,
    }


def product_input_to_update_args(data, product_id) -> dict:
    """Argumentos nomeados de `fn_update_products`.

    Sem `p_company_id` de propósito: a função resolve a empresa a partir da
    própria linha do produto. Recebê-la do chamador deixaria qualquer um
    editar produto de outra empresa bastando informar uma onde ele é ADMIN.

    Todos os campos vão preenchidos porque o formulário entrega a tela
    inteira; a semântica "NULL = não alterar" da função fica disponível para
    um chamador parcial (importação, ajuste em lote), não para este.

    `active` NÃO entra: quem muda situação de cadastro é
    `fn_set_product_active`, e misturar as duas faria uma edição de preço
    reativar em silêncio um produto desativado.
    """
    return {
        "p_product_id": product_id,
        "p_barcode": data.code,
        "p_name": data.name,
        "p_sell_price": str(money_to_db(data.sale_price)),
        "p_buy_price": str(money_to_db(data.cost)),
        "p_unit": unit_to_db(data.unit),
        "p_stock": to_int(data.stock),
        "p_item_category": data.category,
    }
