from enum import StrEnum


class PurchaseStatus(StrEnum):
    RASCUNHO = "RASCUNHO"
    RECEBIDA = "RECEBIDA"

    @property
    def label(self) -> str:
        return {
            PurchaseStatus.RASCUNHO: "Rascunho",
            PurchaseStatus.RECEBIDA: "Recebida",
        }[self]

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Status de compra inválido: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Status de compra desconhecido: {value!r}") from None
