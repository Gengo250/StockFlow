"""Contratos de consulta/reversão US17 e devolução idempotente US20."""

from typing import Protocol, TypedDict

from stockflow.application.dto.return_dto import ReturnResultDTO
from stockflow.application.dto.sale_filter import SaleFilter, SalePage


class ReturnItemPayload(TypedDict):
    sale_item_id: str
    quantity: int


class SaleRepository(Protocol):
    def list_page(self, filtro: SaleFilter, page: int, size: int) -> SalePage: ...

    def get(self, sale_id: str) -> dict | None: ...

    def cancel(self, sale_id: str, reason: str) -> dict: ...

    def revert(self, sale_id: str, reason: str) -> dict: ...

    def list_all(self) -> list: ...

    def get_returnable_items(self, sale_id: str) -> list[dict]: ...

    def partial_return(
        self, sale_id: str, items: list[ReturnItemPayload], reason: str,
        idempotency_key: str,
    ) -> ReturnResultDTO: ...
