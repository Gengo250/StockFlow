"""Motivo de um ajuste manual de inventário, espelhando `public.adjustment_reason`."""

from enum import StrEnum


class AdjustmentReason(StrEnum):
    """Lista fechada, e não texto livre.

    "Quanto sumiu por quebra neste mês" precisa ser consulta, não leitura de
    observações — e motivo inválido vira erro de TIPO no Postgres, que é a
    recusa mais barata que existe. O texto descritivo continua existindo em
    `note`, como detalhe do motivo, nunca como substituto dele.
    """

    CONTAGEM = "CONTAGEM"
    QUEBRA = "QUEBRA"
    PERDA = "PERDA"
    VENCIMENTO = "VENCIMENTO"
    DEVOLUCAO = "DEVOLUCAO"
    OUTRO = "OUTRO"

    @property
    def label(self) -> str:
        return {
            AdjustmentReason.CONTAGEM: "Erro de contagem",
            AdjustmentReason.QUEBRA: "Quebra / avaria",
            AdjustmentReason.PERDA: "Perda / furto",
            AdjustmentReason.VENCIMENTO: "Vencimento",
            AdjustmentReason.DEVOLUCAO: "Devolução de cliente",
            AdjustmentReason.OUTRO: "Outro",
        }[self]

    @property
    def exige_detalhe(self) -> bool:
        """`OUTRO` sem texto não diz nada — é o motivo que não é motivo.

        Espelha o CHECK `ck_movements_adjustment_detail` da tabela, para que
        a tela recuse antes de gastar a requisição que o banco recusaria.
        """
        return self is AdjustmentReason.OUTRO

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Motivo de ajuste inválido: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Motivo de ajuste desconhecido: {value!r}") from None
