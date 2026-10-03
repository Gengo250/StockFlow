"""Operações que consomem produto do catálogo (US02)."""

from enum import StrEnum


class OperationKind(StrEnum):
    """As três operações que precisam validar a situação do produto.

    A lista existe para que a mensagem de recusa diga em qual operação o
    produto foi barrado. Um módulo novo que consuma produto entra aqui — e
    não cria a sua própria frase de erro.
    """

    COMPRA = "COMPRA"
    VENDA = "VENDA"
    MOVIMENTACAO = "MOVIMENTACAO"

    @property
    def label(self) -> str:
        """Nome da operação como o usuário a lê na tela."""
        return {
            OperationKind.COMPRA: "compra",
            OperationKind.VENDA: "venda",
            OperationKind.MOVIMENTACAO: "movimentação",
        }[self]

    @classmethod
    def from_value(cls, value):
        """Converte texto ou enum em `OperationKind`.

        Mesma normalização de `UserRole.from_value`: a origem é configuração
        ou UI, em caixa qualquer, e um valor desconhecido precisa estourar em
        vez de virar silenciosamente uma operação sem validação.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Operação inválida: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Operação desconhecida: {value!r}") from None
