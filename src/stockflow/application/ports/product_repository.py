"""Porta de persistência de produtos."""

from typing import Protocol

from stockflow.application.dto.product_input import ProductInput


class ProductRepository(Protocol):
    """Contrato que a infraestrutura deve satisfazer.

    Em uma implementação de banco, as verificações de status devem respeitar
    o escopo RLS da empresa e as gravações devem passar pelas funções
    autorizadas documentadas para o backend.
    """

    def exists(self, code: str) -> bool: ...

    def is_category_active(self, category: str) -> bool: ...

    def is_unit_active(self, unit: str) -> bool: ...

    def list_active_categories(self) -> tuple[str, ...]: ...

    def list_active_units(self) -> tuple[str, ...]: ...

    def create(self, data: ProductInput) -> str:
        """Retorna o code gravado."""
        ...

    def update(self, code: str, data: ProductInput) -> str:
        """Retorna o code gravado."""
        ...
