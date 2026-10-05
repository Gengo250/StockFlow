"""Persistência de clientes, sempre limitada à empresa autenticada."""

from dataclasses import replace

from stockflow.domain.entities.client import Client
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.validators.client import normalize_document


class SupabaseClientRepository:
    def __init__(self, client, company_id, role=None):
        self._client, self._company_id, self._role = client, company_id, role

    def _rpc(self, name, args):
        try:
            return self._client.rpc(name, args).execute().data
        except Exception as error:
            if str(getattr(error, "code", "")) == "42501":
                raise PermissionDeniedError("gerenciar clientes", self._role) from error
            raise

    def search(self, query=""):
        rows = self._rpc("fn_list_company_clients", {
            "p_company_id": self._company_id, "p_search": query or None,
        }) or []
        return tuple(Client(
            client_id=str(row["client_id"]), name=row["name"],
            document=row.get("document") or "", email=row.get("email") or "",
            phone=row.get("phone") or "", notes=row.get("notes") or "",
            active=bool(row["active"]),
        ) for row in rows)

    def list_all(self):
        return self.search()

    def get(self, client_id):
        return next((c for c in self.list_all() if c.client_id == client_id), None)

    def exists(self, client_id):
        return self.get(client_id) is not None

    def find_by_document(self, document):
        return next((c for c in self.search(document)
                     if c.document == normalize_document(document)), None)

    def next_id(self):
        return None  # The database generates the definitive UUID.

    @staticmethod
    def _args(data):
        return {"p_name": data.name, "p_document": data.document or None,
                "p_email": data.email or "", "p_phone": data.phone or "",
                "p_notes": data.notes or ""}

    def create(self, data):
        client_id = str(self._rpc("fn_create_client", {
            **self._args(data), "p_company_id": self._company_id,
        }))
        if data.active is False:
            self.set_active(client_id, False)
        return self.get(client_id)

    def update(self, client_id, data):
        self._rpc("fn_update_client", {
            **self._args(data), "p_client_id": client_id, "p_active": data.active,
        })
        return self.get(client_id)

    def set_active(self, client_id, active):
        self._rpc("fn_set_client_active", {
            "p_client_id": client_id, "p_active": bool(active),
        })
