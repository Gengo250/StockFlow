"""Seleção de produto pelos módulos que consomem o catálogo (US02).

Compras, vendas e movimentações precisam das mesmas duas coisas: a lista do
que pode ser oferecido e a recusa do que não pode ser gravado. Deixar cada
módulo resolver o código no catálogo e olhar `active` por conta própria é o
caminho pelo qual um deles esquece — e o produto desativado volta a ser
vendável por uma tela só.

Não recebe sessão: escolher produto para uma operação não é escrever no
catálogo. A permissão de papel continua sendo do `ProductService`, e
misturar as duas aqui negaria venda ao SELLER, que é exatamente quem vende.
"""

from stockflow.application.ports.product_repository import ProductRepository
from stockflow.domain.product_status import (
    ensure_product_selectable,
    selectable_products,
)


class ProductSelectionService:
    def __init__(self, repository: ProductRepository):
        self._repository = repository

    def available_products(self) -> tuple:
        """Produtos oferecíveis agora, na ordem do catálogo.

        Relê o repositório a cada chamada de propósito. O catálogo é o mesmo
        dict que a tela de Estoque grava, e a tela de Vendas fica aberta
        enquanto ele muda: uma lista guardada na construção ofereceria a
        foto do catálogo no momento em que a tela abriu.
        """
        return selectable_products(self._repository.list_all())

    def ensure_selectable(self, code: str, operation):
        """Valida o código escolhido e devolve o produto.

        Resolver antes de validar é o que separa "não existe" de "está
        inativo": o primeiro é divergência entre o módulo e o catálogo, o
        segundo é a regra da US02 funcionando.
        """
        return ensure_product_selectable(
            self._repository.get(code), operation, code=code
        )
