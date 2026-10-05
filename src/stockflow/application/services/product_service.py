"""Casos de uso de escrita no catálogo de produtos."""

from stockflow.application.dto.product_input import ProductInput
from stockflow.application.ports.product_repository import ProductRepository
from stockflow.domain.permissions import ensure_can_manage_products
from stockflow.domain.validators.product import validate_product


class ProductService:
    def __init__(self, repository: ProductRepository, supplier_repository=None):
        self._repository = repository
        self._supplier_repository = supplier_repository

    def create_product(self, session, data: ProductInput) -> str:
        """Cadastra um produto. Levanta `ValueError` se o código já existir."""
        # A permissão é verificada antes de QUALQUER chamada ao repositório,
        # inclusive `exists()`: usuário sem permissão não pode nem sondar o
        # catálogo para descobrir quais códigos existem.
        ensure_can_manage_products(session, action="cadastrar produtos")

        if self._repository.exists(data.code):
            raise ValueError(f"Já existe um produto com o código {data.code}.")
        validate_product(
            data,
            category_is_active=self._repository.is_category_active,
            unit_is_active=self._repository.is_unit_active,
        )
        self._validate_supplier(data)
        return self._repository.create(data)

    def update_product(self, session, code: str, data: ProductInput) -> str:
        """Edita um produto. Levanta `LookupError` se o código não existir."""
        ensure_can_manage_products(session, action="editar produtos")

        if not self._repository.exists(code):
            raise LookupError(f"Produto {code} não encontrado.")

        if data.code != code and self._repository.exists(data.code):
            raise ValueError(f"Já existe um produto com o código {data.code}.")

        validate_product(
            data,
            category_is_active=self._repository.is_category_active,
            unit_is_active=self._repository.is_unit_active,
        )
        get_current = getattr(self._repository, "get", None)
        current = get_current(code) if get_current is not None else None
        self._validate_supplier(data, current)
        return self._repository.update(code, data)

    def list_categories(self) -> tuple[str, ...]:
        return tuple(self._repository.list_active_categories())

    def create_category(self, session, name: str) -> str:
        """Cadastra uma categoria. Espelha `fn_create_categories`.

        A recusa de nome repetido acontece aqui para a tela poder explicar o
        motivo: o banco responde a mesma violação como `unique_violation`,
        que chegaria à interface como erro de persistência. A comparação
        ignora caixa e espaços porque `UNIQUE (company_id, name)` só pegaria
        a repetição literal, e duas categorias "Eletrônicos"/"eletronicos  "
        na mesma empresa são a mesma categoria para quem usa o combo.
        """
        ensure_can_manage_products(session, action="cadastrar categorias")

        nome = (name or "").strip()
        if not nome:
            raise ValueError("Informe o nome da categoria.")

        existentes = {c.casefold(): c for c in self._repository.list_active_categories()}
        if nome.casefold() in existentes:
            raise ValueError(f"A categoria {existentes[nome.casefold()]} já existe.")

        self._repository.create_category(nome)
        return nome

    def _validate_supplier(self, data, current=None):
        if not data.supplier_id or self._supplier_repository is None:
            return
        supplier = self._supplier_repository.get(data.supplier_id)
        if supplier is None or (
            not supplier.active
            and getattr(current, "supplier_id", None) != data.supplier_id
        ):
            raise ValueError("Selecione um fornecedor ativo para o produto.")
