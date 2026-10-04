"""Porta para persistência de clientes."""

from typing import Protocol

from stockflow.application.dto.client_input import ClientInput
from stockflow.domain.entities.client import Client


class ClientRepository(Protocol):
    def list_all(self) -> tuple[Client, ...]:
        ...

    def search(self, query: str) -> tuple[Client, ...]:
        ...

    def find_by_document(self, document: str) -> Client | None:
        ...

    def get(self, client_id: str) -> Client | None:
        ...

    def exists(self, client_id: str) -> bool:
        ...

    def create(self, data: ClientInput) -> Client:
        ...

    def update(self, client_id: str, data: ClientInput) -> Client:
        ...

    def set_active(self, client_id: str, active: bool) -> None:
        ...

    def next_id(self) -> str:
        ...
