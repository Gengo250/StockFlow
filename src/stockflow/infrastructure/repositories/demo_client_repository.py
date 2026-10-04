"""Adaptador de clientes em memória."""

import dataclasses

from stockflow.application.dto.client_input import ClientInput
from stockflow.domain.entities.client import Client
from stockflow.presentation.demo_data import DEMO_PEOPLE, is_demo_client_active, set_demo_client_active


def _to_client(data: ClientInput) -> Client:
    return Client(
        client_id=data.client_id or "CLI-000",
        name=(data.name or "").strip(),
        email=(data.email or "").strip(),
        phone=(data.phone or "").strip(),
        document=(data.document or "").strip(),
        active=bool(data.active),
        notes=(data.notes or "").strip(),
    )


class DemoClientRepository:
    def __init__(self, clients=None):
        if clients is None:
            self._clients = {p.cliente_id: Client(
                client_id=p.cliente_id,
                name=p.name,
                email=p.login,
                phone="",
                document="",
                active=is_demo_client_active(p.cliente_id, default=p.status != "Inativo"),
                notes="",
            ) for p in DEMO_PEOPLE}
        else:
            self._clients = dict(clients)

    def list_all(self):
        return tuple(self._clients.values())

    def get(self, client_id: str):
        return self._clients.get(client_id)

    def exists(self, client_id: str) -> bool:
        return client_id in self._clients

    def next_id(self) -> str:
        prefix = "CLI-"
        maior = 0
        for code in self._clients:
            codigo = str(code)
            if codigo.startswith(prefix):
                sufixo = codigo[len(prefix):]
                if sufixo.isdigit():
                    maior = max(maior, int(sufixo))
        numero = maior + 1
        while f"{prefix}{numero:0>3}" in self._clients:
            numero += 1
        return f"{prefix}{numero:0>3}"

    def create(self, data: ClientInput):
        cliente = _to_client(data)
        self._clients[cliente.client_id] = cliente
        return cliente

    def update(self, client_id: str, data: ClientInput):
        existente = self._clients.get(client_id)
        if existente is None:
            raise LookupError(f"Cliente {client_id} não encontrado.")
        atualizado = dataclasses.replace(
            existente,
            name=(data.name or existente.name).strip(),
            email=(data.email if data.email is not None else existente.email).strip(),
            phone=(data.phone if data.phone is not None else existente.phone).strip(),
            document=(data.document if data.document is not None else existente.document).strip(),
            active=bool(data.active if data.active is not None else existente.active),
            notes=(data.notes if data.notes is not None else existente.notes).strip(),
        )
        self._clients[client_id] = atualizado
        return atualizado

    def set_active(self, client_id: str, active: bool) -> None:
        if client_id not in self._clients:
            raise LookupError(f"Cliente {client_id} não encontrado.")
        self._clients[client_id].active = bool(active)
        set_demo_client_active(client_id, bool(active))
