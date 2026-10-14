"""DTO que representa um item individual em um registro de venda."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SaleItemInput:
    """Dados de um item que compõe uma venda."""

    product_code: str
    quantity: int


def validate_sale_items(items: tuple[SaleItemInput, ...]) -> None:
    """Valida itens de venda antes do registro.

    Lança ValueError se:
    - Não houver itens
    - Qualquer produto não for ativo
    - Qualquer quantidade for inválida (≤ 0)
    - Qualquer produto possuir estoque insuficiente
    """
    if not items:
        raise ValueError("A venda deve ter pelo menos um item.")

    for item in items:
        if isinstance(item.quantity, bool) or not isinstance(item.quantity, int):
            raise ValueError(
                f"Quantidade inválida para o produto {item.product_code}: "
                "informe um número inteiro."
            )
        if item.quantity <= 0:
            raise ValueError(
                f"Quantidade inválida para o produto {item.product_code}: "
                "deve ser maior que zero."
            )


class SaleItemValidator:
    """Validador de itens com checagem de produto ativo e saldo."""

    def __init__(self, product_repository):
        self._product_repository = product_repository

    def validate(self, items: tuple[SaleItemInput, ...]) -> None:
        """Validates all items: active products, valid quantities, and sufficient stock.

        Raises:
            ValueError: If any validation fails.
        """
        validate_sale_items(items)
        products = {}
        quantities = {}
        for item in items:
            if item.product_code not in products:
                product = self._product_repository.get(item.product_code)
                if product is None:
                    raise ValueError(
                        f"O produto {item.product_code} não existe."
                    )
                if not getattr(product, "active", False):
                    raise ValueError(
                        f"Produto {product.code} ({product.name}) está inativo "
                        "e não pode ser vendido."
                    )
                products[item.product_code] = product
            quantities[item.product_code] = (
                quantities.get(item.product_code, 0) + item.quantity
            )

        for code, quantity in quantities.items():
            available = self.current_stock(products[code])
            if quantity > available:
                raise ValueError(
                    f"Estoque insuficiente para o produto {code}: "
                    f"solicitado {quantity}, disponível {available}."
                )

    @staticmethod
    def current_stock(product) -> int:
        """Obtém o estoque atual do produto."""
        try:
            stock_str = str(getattr(product, "stock", "0")).strip()
            if not stock_str:
                raise ValueError("Saldo do produto vazio.")
            stock = int(stock_str)
            if stock < 0:
                raise ValueError("Saldo do produto negativo.")
            return stock
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"Saldo inválido para o produto {getattr(product, 'code', '')}."
            ) from error
