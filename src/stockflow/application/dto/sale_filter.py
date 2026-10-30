"""Filtro e página do histórico de vendas (US17)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

ORDENACOES = (
    ("DATA_DESC", "Mais recentes primeiro"),
    ("DATA_ASC", "Mais antigas primeiro"),
    ("VALOR_DESC", "Maior valor"),
    ("VALOR_ASC", "Menor valor"),
    ("CLIENTE_ASC", "Cliente (A-Z)"),
)
TAMANHO_PADRAO = 50
TAMANHO_MAXIMO = 200
MOTIVO_MAXIMO = 300


@dataclass(frozen=True)
class SaleFilter:
    """date_to é inclusivo; o adaptador converte para limite exclusivo."""

    sale_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    client_id: str | None = None
    seller_id: str | None = None
    status: str | None = None
    sort: str = "DATA_DESC"

    def __post_init__(self):
        if self.sort not in {codigo for codigo, _ in ORDENACOES}:
            raise ValueError(f"Ordenação desconhecida: {self.sort!r}")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("A data inicial não pode ser depois da final.")

    def com(self, **campos) -> "SaleFilter":
        return replace(self, **campos)

    @property
    def ativo(self) -> bool:
        return any((self.sale_id, self.date_from, self.date_to,
                    self.client_id, self.seller_id, self.status))


@dataclass(frozen=True)
class SalePage:
    rows: tuple
    total: int
    page: int
    size: int

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.size)) if self.size > 0 else 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1
