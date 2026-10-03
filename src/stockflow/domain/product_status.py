"""Política de situação do produto para novas operações (US02).

Espelha `active` de `public.products` e a função
`database/code/procedures/05_catalog.sql::fn_set_product_active`, que faz o
soft-delete. O comentário daquela função já diz o contrato que esta política
completa: desativar esconde o produto da UI, não do banco — a policy de
SELECT não filtra por `active`, justamente para que o histórico continue
resolvendo a FK.

Daí a divisão aqui:

- Caminho de ESCRITA (nova compra, nova venda, nova movimentação): passa por
  `ensure_product_selectable` e recusa inativo.
- Caminho de LEITURA de operação já registrada: não passa por aqui. A
  operação guarda o produto que foi associado quando ela aconteceu, e
  desativar o cadastro depois não pode apagar esse vínculo.
"""

from stockflow.domain.enums.operation_kind import OperationKind
from stockflow.domain.exceptions.inactive_product import InactiveProductError
from stockflow.domain.exceptions.product_not_found import ProductNotFoundError


def is_product_selectable(product) -> bool:
    """Diz se o produto pode entrar numa operação nova.

    Falha fechada em dois casos: produto ausente (`None`) e objeto que não
    declara `active`. Os dois significam "não foi possível confirmar que
    está ativo", e responder `True` aí liberaria exatamente o cadastro que a
    US02 existe para bloquear.
    """
    if product is None:
        return False
    return getattr(product, "active", False) is True


def ensure_product_selectable(product, operation, code: str | None = None):
    """Valida a seleção do produto e o devolve, para encadear na chamada.

    `code` é o código pedido pelo chamador. Serve para nomear o produto
    ausente na mensagem, já que nesse caso não há objeto de onde tirá-lo.
    """
    operation = OperationKind.from_value(operation)

    if product is None:
        raise ProductNotFoundError(code if code is not None else "desconhecido")

    if not is_product_selectable(product):
        raise InactiveProductError(
            getattr(product, "code", code),
            getattr(product, "name", None),
            operation,
        )

    return product


def selectable_products(catalog) -> tuple:
    """Produtos que podem ser oferecidos para escolha, na ordem do catálogo.

    Aceita o dict `code -> Product` que as telas compartilham e também uma
    sequência de produtos, porque nem todo consumidor tem o catálogo
    indexado. A ordem é preservada: a lista de seleção não pode reordenar
    sozinha o que o usuário já aprendeu a procurar.
    """
    itens = catalog.values() if hasattr(catalog, "values") else catalog
    return tuple(item for item in itens if is_product_selectable(item))
