"""Campo auditado numa linha de `price_edit_log`, espelhando `public.price_edit_field`."""

from enum import StrEnum


class PriceEditField(StrEnum):
    """Qual dos dois valores do produto a linha descreve.

    Lista fechada pela mesma razão de `AdjustmentReason`: "quanto o custo
    subiu neste trimestre" precisa ser consulta, e campo auditado em texto
    livre aceitaria três grafias do mesmo campo na mesma coluna.
    """

    SELL_PRICE = "SELL_PRICE"
    BUY_PRICE = "BUY_PRICE"

    @property
    def label(self) -> str:
        """Rótulo curto: a coluna da tabela é estreita e a linha já diz o resto."""
        return {
            PriceEditField.SELL_PRICE: "Venda",
            PriceEditField.BUY_PRICE: "Custo",
        }[self]

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Campo de preço inválido: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Campo de preço desconhecido: {value!r}") from None
