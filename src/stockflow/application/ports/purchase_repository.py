from typing import Protocol

from stockflow.application.dto.purchase_input import PurchaseInput


class PurchaseRepository(Protocol):
    def list_all(self) -> tuple:
        ...

    def create(self, data: PurchaseInput) -> str:
        ...

    def receive(self, purchase_id: str) -> None:
        ...
