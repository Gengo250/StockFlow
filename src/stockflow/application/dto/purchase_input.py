from dataclasses import dataclass


@dataclass(frozen=True)
class PurchaseItemInput:
    product_code: str
    quantity: int


@dataclass(frozen=True)
class PurchaseInput:
    supplier_id: str
    items: tuple[PurchaseItemInput, ...]
