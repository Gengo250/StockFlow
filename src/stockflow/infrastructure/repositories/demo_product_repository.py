"""Adaptador de `ProductRepository` sobre o catálogo em memória da demonstração.

Enquanto a persistência no Supabase não entra, a `MainWindow` mantém um dict
`code -> Product`. Este adaptador escreve nesse mesmo dict, para que a regra
de permissão já passe pelo `ProductService` real — trocar por um repositório
de banco depois não muda nada acima desta camada.
"""

import dataclasses

from stockflow.application.dto.product_input import ProductInput
from stockflow.domain.enums.product_unit import PRODUCT_UNITS
# Reexportados: a regra de status virou domínio na US04
# (`stockflow.domain.stock_level`), mas ela nasceu aqui e os consumidores
# existentes importam deste módulo. Reexportar mantém o caminho antigo
# válido sem deixar duas implementações da mesma regra no repositório.
from stockflow.domain.stock_level import (  # noqa: F401
    DEFAULT_MINIMUM_STOCK,
    NOT_CONFIGURED,
    derive_stock_status,
    is_below_minimum,
    to_min,
)

# Sentinela para "o DTO nem tem o campo", distinto de "o campo veio ausente".
# Desde que `None` virou valor de domínio (mínimo não configurado), usar
# `None` para os dois faria a ausência DELIBERADA ser sobrescrita pelo padrão
# do repositório — o produto ganharia um limiar que ninguém pediu.
_SEM_CAMPO = object()

# Depender da apresentação é uma inversão aceita só enquanto o `Product` da
# demonstração é o único modelo de leitura existente. O adaptador de banco vai
# nascer com o seu próprio, e este arquivo sai junto com o dict em memória.
from stockflow.presentation.demo_products import Product

ACTIVE_DEMO_CATEGORIES = frozenset({"Eletrônicos", "Periféricos"})
ACTIVE_DEMO_UNITS = frozenset(PRODUCT_UNITS)


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
    def __init__(
        self,
        products: dict,
        minimum_stock=NOT_CONFIGURED,
        active_categories=None,
        active_units=ACTIVE_DEMO_UNITS,
    ):
        self._products = products
        self._minimum_stock = minimum_stock
        self._active_categories = (
            set(ACTIVE_DEMO_CATEGORIES)
            if active_categories is None
            else set(active_categories)
        )
        self._active_units = set(active_units)

    def exists(self, code: str) -> bool:
        return code in self._products

    def is_category_active(self, category: str) -> bool:
        return category in self._active_categories

    def is_unit_active(self, unit: str) -> bool:
        return unit in self._active_units

    def list_active_categories(self) -> tuple[str, ...]:
        return tuple(sorted(self._active_categories))

    def list_active_units(self) -> tuple[str, ...]:
        return tuple(unit for unit in PRODUCT_UNITS if unit in self._active_units)
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

    def list_alerts(self) -> tuple:
        """Mesma regra de `vw_stock_alerts`, aplicada ao catálogo em memória.

        Sem banco não há view, então o critério vive aqui — mas vive em UM
        lugar, e não espalhado pela tela. `derive_stock_status` é o espelho
        declarado de `fn_stock_state`, com teste de grade comparando os dois
        caso a caso.
        """
        alertas = []
        for produto in self._products.values():
            if not produto.active:
                continue
            minimo = to_min(getattr(produto, "minimum_stock", None))
            if minimo is None:
                continue
            situacao = derive_stock_status(produto.stock, minimo)
            if is_below_minimum(situacao):
                alertas.append((produto.code, produto.stock, minimo, situacao))
        return tuple(alertas)

    def set_active(self, code: str, active: bool) -> None:
        """Soft-delete no catálogo em memória.

        Idempotente de propósito: a tela de Estoque já altera a própria linha
        antes de avisar a janela, então este método costuma receber o valor
        que o dict já tem. Falhar aí seria transformar sincronia em erro.
        """
        atual = self._products.get(code)
        if atual is None:
            raise LookupError(f"Produto {code} não encontrado.")
        self._products[code] = dataclasses.replace(atual, active=bool(active))

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
        # O mínimo vem do PRODUTO (US04); `self._minimum_stock` só entra
        # quando o chamador não declara um — importação, API ou qualquer
        # DTO anterior ao campo existir. Usar sempre o do repositório
        # devolveria o limiar global que a US04 veio substituir.
        minimo = getattr(data, "minimum_stock", _SEM_CAMPO)
        if minimo is _SEM_CAMPO:
            minimo = self._minimum_stock
        return Product(
            code=data.code,
            name=data.name,
            category=data.category,
            unit=data.unit,
            sale_price=data.sale_price,
            cost=data.cost,
            active=data.active,
            stock=str(stock),
            stock_status=derive_stock_status(stock, minimo),
            minimum_stock=to_min(minimo),
            supplier_id=getattr(data, "supplier_id", None),
        )
