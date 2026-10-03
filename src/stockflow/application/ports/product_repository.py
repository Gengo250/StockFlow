"""Porta de persistência de produtos."""

from typing import Protocol

from stockflow.application.dto.product_input import ProductInput


class ProductRepository(Protocol):
    """Contrato que a infraestrutura (Supabase) deve satisfazer."""

    def exists(self, code: str) -> bool: ...

    def get(self, code: str):
        """Produto gravado sob o código, ou `None` se não houver.

        Devolver `None` em vez de levantar é deliberado: quem chama precisa
        distinguir ausência de inativo, e a distinção é da política (US02),
        não da persistência.
        """
        ...

    def list_all(self):
        """Catálogo inteiro, na ordem de cadastro — inativos inclusive.

        Filtrar aqui seria esconder o inativo também de quem precisa dele:
        a listagem do catálogo, a ficha do produto e a consulta de operações
        antigas.
        """
        ...

    def create(self, data: ProductInput) -> str:
        """Retorna o code gravado."""
        ...

    def update(self, code: str, data: ProductInput) -> str:
        """Retorna o code gravado."""
        ...
