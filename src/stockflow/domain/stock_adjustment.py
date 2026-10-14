"""Aritmética do ajuste manual de inventário (H11).

O operador informa o saldo CONTADO e o sistema deriva o lançamento. Esta
função é a tradução literal do `IF p_counted_balance > v_current` de
`fn_register_adjustment`, e existe para que a prévia da tela e a validação
do serviço não sejam duas contas que podem discordar.
"""

from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.exceptions.adjustment_errors import AjusteSemEfeitoError


def calcular_ajuste(saldo_atual: int, contado: int) -> tuple[MovementKind, int]:
    """Espécie e quantidade POSITIVA que levam `saldo_atual` até `contado`.

    Quantidade positiva, com o sinal morando na espécie: é o mesmo contrato
    de `stock_movements`, que tem `CHECK (quantity > 0)`. Devolver um
    inteiro com sinal colocaria a mesma informação em dois lugares.
    """
    saldo_atual = int(saldo_atual)
    contado = int(contado)

    if contado < 0:
        raise ValueError(f"O saldo contado não pode ser negativo (recebido: {contado}).")
    if contado == saldo_atual:
        raise AjusteSemEfeitoError(saldo_atual)
    if contado > saldo_atual:
        return MovementKind.ENTRADA, contado - saldo_atual
    return MovementKind.SAIDA, saldo_atual - contado
