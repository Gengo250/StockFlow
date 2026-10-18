"""Dados de um ajuste manual como a tela os entrega (H11)."""

from dataclasses import dataclass

from stockflow.domain.enums.adjustment_reason import AdjustmentReason


@dataclass(frozen=True)
class AdjustmentInput:
    """Campos de `fn_register_adjustment`, menos a identidade.

    `created_by` NÃO entra aqui, pela mesma razão de `MovementInput`: quem
    ajusta é a sessão, e o banco a resolve por `fn_current_user_id()`.
    Aceitar um identificador vindo da tela permitiria registrar o ajuste em
    nome de outra pessoa — e ajuste manual é justamente a operação que
    precisa de autor confiável.

    `expected_balance` é o saldo que a TELA exibiu, não um palpite: a função
    recusa quando ele não bate com o saldo real, porque entre a contagem e o
    clique alguém pode ter movimentado o mesmo produto.

    `None` em `expected_balance` é o OPT-OUT dessa checagem, e é por isso que
    o tipo é `int | None`: é assim que `fn_register_adjustment` a pula
    (`IF p_expected_balance IS NOT NULL AND ...`) e é assim que os dois
    adaptadores a leem. Quem chama sem saldo exibido — um script de
    reconciliação, um teste — diz explicitamente "não tenho o que comparar",
    em vez de inventar um número que a função confrontaria com o saldo real.
    A tela SEMPRE informa o saldo que mostrou; o opt-out não é para ela.
    """

    product_code: str
    counted_balance: int
    expected_balance: int | None
    reason: AdjustmentReason
    detail: str = ""
