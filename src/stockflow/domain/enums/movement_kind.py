"""Espécies de movimentação de estoque, espelhando `public.movement_kind`."""

from enum import StrEnum


class MovementKind(StrEnum):
    """Duas espécies, não três.

    ENTRADA e SAIDA, as duas com quantidade POSITIVA. "Ajuste" não é uma
    terceira espécie: é uma entrada ou uma saída com justificativa na nota.
    Um tipo de sinal variável exigiria afrouxar o `CHECK (quantity > 0)` da
    tabela e deixaria o sinal escondido no dado, onde ninguém lê.
    """

    ENTRADA = "ENTRADA"
    SAIDA = "SAIDA"

    @property
    def label(self) -> str:
        return {MovementKind.ENTRADA: "Entrada",
                MovementKind.SAIDA: "Saída"}[self]

    @property
    def sinal(self) -> int:
        """Quanto esta espécie soma ao saldo, por unidade.

        Espelha o `CASE` de `fn_confirmed_balance`. Existe para que quem
        precise projetar um saldo não reescreva a regra do sinal.
        """
        return 1 if self is MovementKind.ENTRADA else -1

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Espécie de movimentação inválida: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Espécie desconhecida: {value!r}") from None
