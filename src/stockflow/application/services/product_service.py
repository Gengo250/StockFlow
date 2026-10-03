"""Casos de uso de escrita no catálogo de produtos."""

from stockflow.application.dto.product_input import ProductInput
from stockflow.application.ports.product_repository import ProductRepository
from stockflow.domain.permissions import ensure_can_manage_products


class ProductService:
    def __init__(self, repository: ProductRepository):
        self._repository = repository

    def create_product(self, session, data: ProductInput) -> str:
        """Cadastra um produto. Levanta `ValueError` se o código já existir."""
        # A permissão é verificada antes de QUALQUER chamada ao repositório,
        # inclusive `exists()`: usuário sem permissão não pode nem sondar o
        # catálogo para descobrir quais códigos existem.
        ensure_can_manage_products(session, action="cadastrar produtos")

        if self._repository.exists(data.code):
            raise ValueError(f"Já existe um produto com o código {data.code}.")
        return self._repository.create(data)

    def update_product(self, session, code: str, data: ProductInput) -> str:
        """Edita um produto. Levanta `LookupError` se o código não existir."""
        ensure_can_manage_products(session, action="editar produtos")

        if not self._repository.exists(code):
            raise LookupError(f"Produto {code} não encontrado.")
        return self._repository.update(code, data)
