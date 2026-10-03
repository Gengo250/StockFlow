"""Porta de persistência de produtos."""

from typing import Protocol

from stockflow.application.dto.product_input import ProductInput


class ProductRepository(Protocol):
    """Contrato que a infraestrutura (Supabase) deve satisfazer."""

    def exists(self, code: str) -> bool: ...

    def create(self, data: ProductInput) -> str:
        """Retorna o code gravado."""
        ...

    def update(self, code: str, data: ProductInput) -> str:
        """Retorna o code gravado."""
        ...
