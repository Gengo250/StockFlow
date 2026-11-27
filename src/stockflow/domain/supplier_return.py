"""Registro comercial de devolução ao fornecedor e seus vínculos de estoque."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SupplierReturnItem:
    item_id: str
    product_code: str
    product_name: str
    quantity: int
    reason: str
    movement_id: str


@dataclass(frozen=True)
class SupplierReturn:
    return_id: str
    company_id: str
    supplier_id: str
    supplier_name: str
    purchase_id: str | None
    created_by: str
    created_on: str
    idempotency_key: str
    items: tuple[SupplierReturnItem, ...]
    created_by_name: str = ""
