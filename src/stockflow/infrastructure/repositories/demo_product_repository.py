"""Adaptador de `ProductRepository` sobre o catálogo em memória da demonstração.

Enquanto a persistência no Supabase não entra, a `MainWindow` mantém um dict
`code -> Product`. Este adaptador escreve nesse mesmo dict, para que a regra
de permissão já passe pelo `ProductService` real — trocar por um repositório
de banco depois não muda nada acima desta camada.
"""

from stockflow.application.dto.product_input import ProductInput

# Depender da apresentação é uma inversão aceita só enquanto o `Product` da
# demonstração é o único modelo de leitura existente. O adaptador de banco vai
# nascer com o seu próprio, e este arquivo sai junto com o dict em memória.
from stockflow.presentation.demo_products import Product

# Estoque mínimo provisório. A US04 é quem expõe o campo por produto; até ela
# voltar (o merge levou `apply_filters`/`search_input` da EstoquePage junto),
# usar um valor fixo é melhor do que inventar uma segunda regra de status.
DEFAULT_MINIMUM_STOCK = 10


def derive_stock_status(stock: int, minimum: int = DEFAULT_MINIMUM_STOCK) -> str:
    """Status de estoque pela regra da US04.

    Zero é sempre crítico, inclusive quando o mínimo também é zero: sem
    unidade em mãos não existe situação "normal".
    """
    if stock <= 0 or stock * 2 <= minimum:
        return "Crítico"
    if stock <= minimum:
        return "Baixo"
    return "Normal"


# Formato de código do catálogo: "PRD-" + três dígitos. Mudar aqui muda o
# código sugerido no formulário; os produtos já gravados continuam válidos
# porque a leitura só exige o prefixo e um sufixo numérico.
CODE_PREFIX = "PRD-"
CODE_DIGITS = 3


def next_product_code(products, prefix: str = CODE_PREFIX,
                      digits: int = CODE_DIGITS) -> str:
    """Primeiro código livre acima do maior já usado no catálogo.

    Continua a numeração em vez de preencher buracos: um código removido
    pertence ao histórico do produto que o usava (nota fiscal, movimentação),
    e reatribuí-lo faria dois produtos diferentes dividirem a mesma
    identidade. Catálogo vazio começa em `PRD-001`; códigos fora do padrão
    (um SKU legado digitado à mão, por exemplo) são ignorados na conta, mas
    ainda assim nunca são sobrescritos — daí o laço final.
    """
    maior = 0
    for code in products:
        texto = str(code)
        if not texto.startswith(prefix):
            continue
        sufixo = texto[len(prefix):]
        if sufixo.isdigit():
            maior = max(maior, int(sufixo))
    numero = maior + 1
    while f"{prefix}{numero:0{digits}d}" in products:
        numero += 1
    return f"{prefix}{numero:0{digits}d}"


def _para_inteiro(valor) -> int:
    """Converte o estoque do formulário para inteiro, sem nunca levantar.

    Tudo que não for um inteiro em texto — vazio, `None`, `"abc"`, `"12.5"` —
    vira `0`. Hoje a origem é um `QSpinBox`, que já garante inteiro, então
    nenhum desses casos é alcançável pela UI; a conversão tolerante existe
    para que um chamador futuro (importação de planilha, API) não derrube a
    gravação. Se esse chamador aparecer, ele precisa validar ANTES de chegar
    aqui: `0` é um estoque plausível e um erro silencioso nesta função vira
    "produto zerado" sem aviso.
    """
    try:
        return int(str(valor).strip() or 0)
    except ValueError:
        return 0


class DemoProductRepository:
    def __init__(self, products: dict, minimum_stock: int = DEFAULT_MINIMUM_STOCK):
        self._products = products
        self._minimum_stock = minimum_stock

    def exists(self, code: str) -> bool:
        return code in self._products

    def get(self, code: str):
        """Leitura por código, sem filtrar por situação.

        O inativo continua sendo devolvido: quem decide se ele serve para a
        operação é a política da US02, e a consulta de operações antigas
        depende justamente de ainda alcançá-lo.
        """
        return self._products.get(code)

    def list_all(self):
        """Catálogo na ordem de cadastro, ativos e inativos."""
        return tuple(self._products.values())

    def next_code(self) -> str:
        """Código livre para um cadastro novo, derivado do catálogo atual."""
        return next_product_code(self._products)

    def create(self, data: ProductInput) -> str:
        self._products[data.code] = self._to_product(data)
        return data.code

    def update(self, code: str, data: ProductInput) -> str:
        # O código é somente leitura no formulário, mas se algum dia deixar de
        # ser, trocar a chave sem remover a antiga duplicaria o produto.
        if code != data.code:
            self._products.pop(code, None)
        self._products[data.code] = self._to_product(data)
        return data.code

    def _to_product(self, data: ProductInput) -> Product:
        stock = _para_inteiro(data.stock)
        return Product(
            code=data.code,
            name=data.name,
            category=data.category,
            unit=data.unit,
            sale_price=data.sale_price,
            cost=data.cost,
            active=data.active,
            stock=str(stock),
            stock_status=derive_stock_status(stock, self._minimum_stock),
        )
