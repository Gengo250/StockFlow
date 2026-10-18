"""DTO para registro de venda com múltiplos itens."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stockflow.application.dto.sale_item import SaleItemInput


@dataclass
class SaleRegisterInput:
    """Entrada para registrar uma venda com múltiplos itens."""

    client_id: str
    items: tuple[SaleItemInput, ...]


@dataclass
class SaleItemSummary:
    """Resumo de um item após registro bem-sucedido."""

    product_code: str
    product_name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
