"""Situação de uma venda, espelhando `public.sale_status`."""

from enum import StrEnum


class SaleStatus(StrEnum):
    """Cancelamento e devolução têm elegibilidades distintas.

    `PENDENTE` é carrinho em montagem; `CANCELADA` diz que a venda não
    deveria ter existido; `DEVOLVIDA` diz que existiu e a mercadoria voltou.
    As duas últimas são TERMINAIS, e não por convenção: `sale_reversals` tem
    `UNIQUE (sale_id)`, então o banco recusa a segunda reversão mesmo que
    alguém chegue por outro caminho.
    """

    PENDENTE = "PENDENTE"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"
    DEVOLVIDA = "DEVOLVIDA"

    @property
    def label(self) -> str:
        return {SaleStatus.PENDENTE: "Pendente",
                SaleStatus.CONCLUIDA: "Concluída",
                SaleStatus.CANCELADA: "Cancelada",
                SaleStatus.DEVOLVIDA: "Devolvida"}[self]

    @property
    def revertida(self) -> bool:
        """Venda desfeita. Não entra em total de dinheiro vendido."""
        return self in (SaleStatus.CANCELADA, SaleStatus.DEVOLVIDA)

    @property
    def reversivel(self) -> bool:
        """Somente a venda concluída admite devolução com restituição."""
        return self is SaleStatus.CONCLUIDA

    @property
    def cancelavel(self) -> bool:
        """Elegibilidade por status; pendência não exige restituição (US15).

        Permissões, caixa e devoluções anteriores são verificações adicionais.
        """
        return self in (SaleStatus.PENDENTE, SaleStatus.CONCLUIDA)

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Situação de venda inválida: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Situação desconhecida: {value!r}") from None
