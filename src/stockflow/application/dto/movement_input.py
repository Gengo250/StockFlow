"""Dados de uma movimentação como a tela os entrega."""

from dataclasses import dataclass

from stockflow.domain.enums.movement_kind import MovementKind


@dataclass(eq=False)
class MovementInput:
    """Campos de `fn_register_movement`, menos a identidade.

    Campos adicionais (company_id, movement_kind, justification, user_id) são
    mantidos apenas para compatibilidade com payloads legados.  Eles não são
    usados pelo core da aplicação, mas o adapter os preenche para que os
    testes que enviam dicionários antigos continuem funcionais.
    """

    # Campos essenciais da aplicação
    product_code: str = ""
    kind: MovementKind = None
    quantity: int = 0
    note: str = ""
    supplier_id: str = ""

    # Campos legados – mantidos como strings vazios por padrão
    company_id: str = ""
    movement_kind: str = ""
    justification: str = ""
    user_id: str = ""

    # Flag de confirmação (isto é, já gravado e confirmado no banco)
    confirm: bool = False

