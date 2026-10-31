"""Espécie de reversão de venda, espelhando `public.sale_reversal_kind`."""

from enum import StrEnum


class SaleReversalKind(StrEnum):
    """Cancelar e devolver movem o estoque por mecanismos diferentes.

    `CANCELAMENTO` anula as saídas da venda e deixa o recálculo devolver o
    saldo; `DEVOLUCAO` grava entradas compensatórias e mantém a saída
    original confirmada, preservando no histórico de estoque que a venda
    aconteceu. A distinção vive no banco (`fn_cancel_sale`/`fn_return_sale`)
    e este enum existe para que a tela não a reinvente.
    """

    CANCELAMENTO = "CANCELAMENTO"
    DEVOLUCAO = "DEVOLUCAO"

    @property
    def label(self) -> str:
        return {SaleReversalKind.CANCELAMENTO: "Cancelamento",
                SaleReversalKind.DEVOLUCAO: "Devolução"}[self]

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Espécie de reversão inválida: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Espécie desconhecida: {value!r}") from None
