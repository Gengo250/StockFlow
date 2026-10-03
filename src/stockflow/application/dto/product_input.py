"""Dados de entrada do formulário de produto."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductInput:
    """Campos como a UI os entrega.

    Preço e estoque chegam como texto formatado ("R$ 2.499,90", "18") porque
    é o formato que o formulário PySide6 já usa em `demo_products.Product`.
    A conversão numérica pertence ao adaptador de persistência, não a este DTO.
    """

    code: str
    name: str
    category: str
    unit: str
    sale_price: str
    cost: str
    stock: str
    active: bool = True
