"""Recusas nomeadas do ajuste manual (H11).

As duas herdam de `ValueError` de propósito: `MainWindow` já trata
`ValueError` como "recusa que o usuário lê no card", e herdar mantém o
comportamento correto mesmo onde ninguém escreveu um `except` específico.
"""


class AjusteSemEfeitoError(ValueError):
    """Contado igual ao saldo atual: não há diferença a lançar."""

    def __init__(self, saldo: int):
        self.saldo = saldo
        super().__init__(
            f"O saldo contado é igual ao saldo atual ({saldo}). "
            "Não há ajuste a registrar."
        )


class SaldoDesatualizadoError(ValueError):
    """O saldo mudou entre a contagem e a gravação.

    Não é erro do usuário nem falha do sistema: é pedido de recontagem. Se
    alguém confirmou uma entrada e pôs a mercadoria na prateleira, nem o
    número contado antes nem o saldo de agora descrevem o que está lá.
    """

    @classmethod
    def de_saldos(cls, esperado: int, atual: int) -> "SaldoDesatualizadoError":
        return cls(
            f"O saldo mudou desde a contagem (na tela: {esperado}, agora: "
            f"{atual}). Reconte o produto antes de ajustar."
        )
