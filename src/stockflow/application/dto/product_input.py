"""Dados de entrada do formulário de produto."""

from dataclasses import dataclass

from stockflow.domain.stock_level import NOT_CONFIGURED


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
    # Mínimo por produto (US03/US04). Inteiro, e não texto como `stock`,
    # porque não vem de campo livre: a tela o entrega por `QSpinBox` e o banco
    # o guarda em `product_stock.min_quantity`.
    #
    # O padrão é AUSENTE (`None`), nunca um valor plausível: quem não informa
    # mínimo não está pedindo alerta com limiar 10, está dizendo que não há
    # limiar. E ausente não é zero — zero é a configuração "me avise quando
    # acabar", que alerta com saldo zerado.
    minimum_stock: int | None = NOT_CONFIGURED
    supplier_id: str | None = None
    description: str = ""
    ncm: str = ""
    ean: str = ""
    location: str = ""
    low_stock_alert: bool = True
    image_data: str = ""
