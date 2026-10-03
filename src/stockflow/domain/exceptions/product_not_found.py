"""Erro de produto não encontrado no catálogo."""


class ProductNotFoundError(LookupError):
    """Código pedido por uma operação que não existe no catálogo.

    Separado de `InactiveProductError` de propósito: não existir e estar
    inativo têm causas diferentes — um é divergência entre o módulo e o
    catálogo, o outro é a regra da US02 funcionando. Relatar os dois como
    "inativo" esconde o primeiro.
    """

    def __init__(self, code: str):
        self.product_code = code
        super().__init__(f"O produto {code} não existe no catálogo.")
