"""Situação de uma movimentação, espelhando `public.movement_status`."""

from enum import StrEnum


class MovementStatus(StrEnum):
    """Registrar não é confirmar, e é essa distinção que a US03 pede.

    Só `CONFIRMADA` entra na composição do saldo (`fn_confirmed_balance`
    filtra por ela). `PENDENTE` é uma intenção registrada; `CANCELADA` é uma
    intenção desfeita — e cancelar uma confirmada devolve o saldo, porque o
    trigger recalcula a soma das que seguem confirmadas.
    """

    PENDENTE = "PENDENTE"
    CONFIRMADA = "CONFIRMADA"
    CANCELADA = "CANCELADA"

    @property
    def label(self) -> str:
        return {MovementStatus.PENDENTE: "Pendente",
                MovementStatus.CONFIRMADA: "Confirmada",
                MovementStatus.CANCELADA: "Cancelada"}[self]

    @property
    def afeta_saldo(self) -> bool:
        return self is MovementStatus.CONFIRMADA

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Situação de movimentação inválida: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Situação desconhecida: {value!r}") from None
