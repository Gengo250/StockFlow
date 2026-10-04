"""Adaptador Supabase/PostgREST para gestão de fornecedores."""

from stockflow.application.dto.supplier_input import SupplierInput
from stockflow.domain.entities.supplier import Supplier
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.validators.supplier import normalize_document
from stockflow.infrastructure.repositories.supabase_product_repository import (
    _e_recusa_de_permissao,
)

SUPPLIER_COLUMNS = "id,name,document,phone,email,address,active"
ACTION_BY_RPC = {
    "fn_create_supplier": "cadastrar fornecedores",
    "fn_update_supplier": "editar fornecedores",
    "fn_set_supplier_active": "alterar status de fornecedores",
}


class SupabaseSupplierRepository:
    def __init__(self, client, company_id, role=None):
        self._client = client
        self._company_id = company_id
        self._role = role

    @staticmethod
    def _rows(response):
        return getattr(response, "data", None) or []

    @staticmethod
    def _supplier(row):
        return Supplier(
            supplier_id=str(row["id"]),
            name=row.get("name") or "",
            document=normalize_document(row.get("document")),
            phone=row.get("phone") or "",
            email=row.get("email") or "",
            address=row.get("address") or "",
            active=bool(row.get("active", True)),
        )

    def list_all(self):
        response = self._client.rpc(
            "fn_list_company_suppliers",
            {"p_company_id": self._company_id, "p_search": None},
        ).execute()
        return tuple(self._supplier(row) for row in self._rows(response))

    def list_active(self):
        return tuple(s for s in self.list_all() if s.active)

    def search(self, query: str):
        response = self._client.rpc(
            "fn_list_company_suppliers",
            {"p_company_id": self._company_id, "p_search": query or None},
        ).execute()
        return tuple(self._supplier(row) for row in self._rows(response))

    def find_by_document(self, document: str):
        normalized = normalize_document(document)
        if not normalized:
            return None
        # A busca usa o mesmo banco de dados e é escopada por empresa. CPF/CNPJ
        # é filtrado em memória apenas sobre a resposta já limitada à empresa.
        return next(
            (supplier for supplier in self.list_all()
             if supplier.document == normalized),
            None,
        )

    def get(self, supplier_id: str):
        return next((s for s in self.list_all() if s.supplier_id == supplier_id), None)

    def exists(self, supplier_id: str) -> bool:
        return self.get(supplier_id) is not None

    def next_id(self) -> str | None:
        """A identidade definitiva é gerada pelo Postgres."""
        return None

    def create(self, data: SupplierInput):
        supplier_id = self._rpc(
            "fn_create_supplier",
            {
                "p_company_id": self._company_id,
                "p_name": data.name,
                "p_document": data.document or None,
                "p_phone": data.phone,
                "p_email": data.email,
                "p_address": data.address,
            },
        )
        supplier = Supplier(
            str(supplier_id), data.name, data.document, data.phone, data.email,
            data.address, bool(data.active if data.active is not None else True),
        )
        if not supplier.active:
            self.set_active(supplier.supplier_id, False)
        return supplier

    def update(self, supplier_id: str, data: SupplierInput):
        self._rpc(
            "fn_update_supplier",
            {
                "p_supplier_id": supplier_id,
                "p_name": data.name,
                "p_document": data.document or None,
                "p_phone": data.phone,
                "p_email": data.email,
                "p_address": data.address,
                "p_active": data.active,
            },
        )
        return Supplier(
            supplier_id, data.name, data.document, data.phone, data.email,
            data.address, bool(data.active),
        )

    def set_active(self, supplier_id: str, active: bool) -> None:
        self._rpc(
            "fn_set_supplier_active",
            {"p_supplier_id": supplier_id, "p_active": bool(active)},
        )

    def _rpc(self, name: str, args: dict):
        try:
            response = self._client.rpc(name, args).execute()
        except Exception as error:
            if _e_recusa_de_permissao(error):
                raise PermissionDeniedError(
                    ACTION_BY_RPC.get(name, f"executar {name}"), self._role
                ) from error
            raise
        return getattr(response, "data", None)
