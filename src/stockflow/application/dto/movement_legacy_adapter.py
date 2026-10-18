from __future__ import annotations
from typing import Mapping, Any
from stockflow.application.dto.movement_input import MovementInput
from stockflow.domain.enums.movement_kind import MovementKind
def _as_movement_kind(value: Any) -> MovementKind:
    """Converte a string ou enum legado para ``MovementKind``."""
    if isinstance(value, MovementKind):
        return value
    return MovementKind.from_value(str(value).upper())
def legacy_to_movement_input(payload: Mapping[str, Any]) -> MovementInput:
    """
    Constrói um ``MovementInput`` a partir de um dicionário 
    Campos reconhecidos (todos opcionais):
        - product_code / product_id → ``product_code``
        - kind / movement_kind      → ``kind`` (enum)
        - quantity                  → ``quantity``
        - note                      → ``note``
        - supplier_id               → ``supplier_id`` (padrão: "")
        - company_id, justification, user_id → preservados (não usados no core)
        - confirm                    → ``confirm`` (bool)
    Campos não listados são simplesmente ignorados.
    """
    code = payload.get("product_code") or payload.get("product_id") or ""
    kind_raw = payload.get("kind") or payload.get("movement_kind")
    kind = _as_movement_kind(kind_raw) if kind_raw is not None else None
    return MovementInput(
        product_code=code,
        kind=kind,
        quantity=int(payload.get("quantity", 0)),
        note=payload.get("note", ""),
        supplier_id=payload.get("supplier_id", ""),
        # campos “legados” que a aplicação não usa mas que alguns testes
        # ainda esperam estar presentes:
        company_id=payload.get("company_id", ""),
        movement_kind=payload.get("movement_kind", ""),
        justification=payload.get("justification", ""),
        user_id=payload.get("user_id", ""),
        confirm=bool(payload.get("confirm", False)),
    )