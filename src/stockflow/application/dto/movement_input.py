"""Dados de uma movimentação como a tela os entrega."""

from dataclasses import dataclass

from stockflow.domain.enums.movement_kind import MovementKind


@dataclass(frozen=True)
class MovementInput:
    """Campos de `fn_register_movement`, menos a identidade.

    `created_by` NÃO entra aqui de propósito: quem registra é a sessão, e o
    banco a resolve sozinho por `fn_current_user_id()`. Aceitar um
    identificador vindo da tela permitiria registrar movimentação em nome de
    outro usuário — exatamente o que o critério da US05 proíbe.
    """

    product_code: str
    kind: MovementKind
    quantity: int
    note: str = ""
    supplier_id: str | None = None
    # Registrar e confirmar são passos distintos; confirmar no mesmo ato é
    # atalho para quem está lançando algo que já aconteceu.
    confirm: bool = False
