"""Porta para persistência de clientes."""

from typing import Protocol

from stockflow.application.dto.client_input import ClientInput


class ClientRepository(Protocol):
    def list_all(self):
        ...

    def get(self, client_id: str):
        ...

    def exists(self, client_id: str) -> bool:
        ...

    def create(self, data: ClientInput):
        ...

    def update(self, client_id: str, data: ClientInput):
        ...

    def set_active(self, client_id: str, active: bool) -> None:
        ...

    def next_id(self) -> str:
        ...
