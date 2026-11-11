"""Filtro e página da consulta de auditoria (US25)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Sequence

from stockflow.domain.enums.price_edit_field import PriceEditField

ORDENACOES_AUDITORIA = (
    ("DATA_DESC", "Mais recentes primeiro"),
    ("DATA_ASC", "Mais antigas primeiro"),
)

TAMANHO_PADRAO_AUDITORIA = 50
TAMANHO_MAXIMO_AUDITORIA = 200


@dataclass(frozen=True)
class AuditFilter:
    """Filtros combináveis para a consulta de auditoria.

    Permite filtrar por usuário responsável, período (inclusivo),
    ação auditada (campo de alteração de preço/custo) e entidade (ex.: produto).
    """

    user: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    action: str | PriceEditField | None = None
    entity: str | None = None
    product_code: str | None = None
    sort: str = "DATA_DESC"

    def __post_init__(self):
        if self.sort not in {codigo for codigo, _ in ORDENACOES_AUDITORIA}:
            raise ValueError(f"Ordenação desconhecida: {self.sort!r}")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("A data inicial não pode ser depois da final.")

    def com(self, **campos) -> "AuditFilter":
        """Retorna uma cópia com os campos substituídos."""
        return replace(self, **campos)

    @property
    def ativo(self) -> bool:
        """Indica se algum critério de filtragem foi ativado além da ordenação."""
        return any((
            self.user,
            self.date_from,
            self.date_to,
            self.action,
            self.entity,
            self.product_code,
        ))


@dataclass(frozen=True)
class AuditPage:
    """Uma página do histórico de auditoria e a contagem total de registros."""

    rows: tuple
    total: int
    page: int
    size: int

    @property
    def pages(self) -> int:
        """Total de páginas disponíveis. Lista vazia é página 1 de 1."""
        if self.size <= 0:
            return 1
        return max(1, -(-self.total // self.size))

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1
