"""Caso de uso para manutenção de clientes."""

from stockflow.application.dto.client_input import ClientInput
from stockflow.application.ports.client_repository import ClientRepository
from stockflow.domain.entities.client import Client
from stockflow.domain.validators.client import normalize_document, validate_client


class ClientService:
    def __init__(self, repository: ClientRepository):
        self._repository = repository

    def list_clients(self):
        return self._repository.list_all()

    def search_clients(self, query: str = ""):
        return self._repository.search(query)

    def create_client(self, data: ClientInput) -> Client:
        validate_client(data)
        duplicate = self._duplicate_document(data.document)
        if duplicate is not None:
            raise ValueError("Já existe um cliente com este CPF/CNPJ.")
        client_id = data.client_id or self._repository.next_id()
        nova = Client(
            client_id=client_id,
            name=(data.name or "").strip(),
            email=(data.email or "").strip(),
            phone=(data.phone or "").strip(),
            document=normalize_document(data.document),
            active=bool(data.active if data.active is not None else True),
            notes=(data.notes or "").strip(),
        )
        return self._repository.create(
            ClientInput(
                client_id=client_id,
                name=nova.name,
                email=nova.email,
                phone=nova.phone,
                document=nova.document,
                active=nova.active,
                notes=nova.notes,
            )
        )

    def update_client(self, client_id: str, data: ClientInput) -> Client:
        if not self._repository.exists(client_id):
            raise LookupError(f"Cliente {client_id} não encontrado.")
        validate_client(data)
        duplicate = self._duplicate_document(data.document)
        if duplicate is not None and duplicate.client_id != client_id:
            raise ValueError("Já existe um cliente com este CPF/CNPJ.")
        atual = self._repository.get(client_id)
        if atual is None:
            raise LookupError(f"Cliente {client_id} não encontrado.")
        payload = ClientInput(
            client_id=client_id,
            name=(data.name or atual.name).strip(),
            email=(data.email if data.email is not None else atual.email).strip(),
            phone=(data.phone if data.phone is not None else atual.phone).strip(),
            document=normalize_document(
                data.document if data.document is not None else atual.document
            ),
            active=(data.active if data.active is not None else atual.active),
            notes=(data.notes if data.notes is not None else atual.notes).strip(),
        )
        return self._repository.update(client_id, payload)

    def set_active(self, client_id: str, active: bool) -> Client:
        if not self._repository.exists(client_id):
            raise LookupError(f"Cliente {client_id} não encontrado.")
        self._repository.set_active(client_id, bool(active))
        updated = self._repository.get(client_id)
        if updated is None:
            raise LookupError(f"Cliente {client_id} não encontrado.")
        return updated

    def _duplicate_document(self, document: str | None):
        normalized = normalize_document(document)
        return self._repository.find_by_document(normalized) if normalized else None
