"""Filtro e página do histórico de vendas (US17)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

#: Critérios aceitos por `fn_list_sales`. Lista fechada de propósito: texto
#: do chamador virando `ORDER BY` é injeção, e o banco recusa o que não
#: estiver aqui. O segundo elemento é o rótulo que a tela mostra no combo,
#: para que não exista uma segunda tradução espalhada na apresentação.
ORDENACOES = (
    ("DATA_DESC", "Mais recentes primeiro"),
    ("DATA_ASC", "Mais antigas primeiro"),
    ("VALOR_DESC", "Maior valor"),
    ("VALOR_ASC", "Menor valor"),
    ("CLIENTE_ASC", "Cliente (A-Z)"),
)

TAMANHO_PADRAO = 50
#: Espelha o teto de `fn_list_sales`. Página sem limite é `list_all` com
#: outro nome, e devolveria o volume que a paginação existe para evitar.
TAMANHO_MAXIMO = 200

MOTIVO_MAXIMO = 300


@dataclass(frozen=True)
class SaleFilter:
    """Todos os campos opcionais: sem status, lista vendas finalizadas.

    `date_to` é INCLUSIVO para quem usa a tela — o adaptador soma um dia
    antes de mandar ao banco, onde o limite é exclusivo. Sem essa conversão
    num lugar só, filtrar "até hoje" perderia as vendas de hoje, e cada
    adaptador erraria à sua maneira. `PENDENTE` fica fora da lista padrão,
    mas pode ser consultado escolhendo esse status explicitamente.
    """

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
        """Cópia com campos trocados, para a tela não remontar o filtro."""
        return replace(self, **campos)

    @property
    def ativo(self) -> bool:
        """Se há algum recorte além da ordenação.

        A ordenação fica de fora porque ela sempre tem valor: considerá-la
        faria a tela dizer "filtros ativos" sobre uma lista completa.
        """
        return any((self.sale_id, self.date_from, self.date_to,
                    self.client_id, self.seller_id, self.status))


@dataclass(frozen=True)
class SalePage:
    """Uma página e o total que casa com o filtro.

    `total` vem da MESMA leitura que trouxe as linhas (`count(*) OVER ()`):
    uma segunda consulta de contagem poderia divergir sob concorrência, e a
    tela ofereceria uma página que a consulta seguinte não devolve.
    """

    rows: tuple
    total: int
    page: int
    size: int

    @property
    def pages(self) -> int:
        """Nunca zero: lista vazia continua sendo "página 1 de 1"."""
        if self.size <= 0:
            return 1
        return max(1, -(-self.total // self.size))

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1
