from dataclasses import dataclass

from stockflow.domain.enums.purchase_status import PurchaseStatus


@dataclass(frozen=True)
class PurchaseItem:
    product_code: str
    product_name: str
    quantity: int


@dataclass(frozen=True)
class Purchase:
    purchase_id: str
    supplier_id: str
    supplier_name: str
    status: PurchaseStatus
    items: tuple[PurchaseItem, ...]
    created_on: str = ""
    received_on: str | None = None
