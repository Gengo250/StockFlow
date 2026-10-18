"""Porta de leitura do histórico de preço e custo (H09)."""

from typing import Protocol

from stockflow.domain.price_change import PriceChange


class PriceHistoryRepository(Protocol):
    """Só leitura, e é uma decisão: a auditoria é escrita pelo trigger.

    Dar um método de escrita aqui permitiria ao sistema auditado registrar a
    própria versão do que aconteceu — a mesma razão pela qual
    `policies/01_security.sql` concede só SELECT na tabela.
    """

    def list_price_edits(self, product_code: str | None = None) -> tuple[PriceChange, ...]:
        """Mudanças da empresa, da mais recente para a mais antiga.

        `product_code` ausente devolve a empresa inteira. Código que não
        existe no catálogo devolve vazio, e não a lista toda: um filtro que
        não encontra o alvo não pode virar "sem filtro".
        """
        ...
