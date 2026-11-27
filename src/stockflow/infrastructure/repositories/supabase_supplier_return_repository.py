"""A RPC US30 registra devolução, SAIDAs e auditoria na mesma transação."""
from uuid import UUID

from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.supplier_return import SupplierReturn, SupplierReturnItem
from stockflow.infrastructure.repositories.supabase_product_repository import _e_recusa_de_permissao


def parse_supplier_return(row):
    try:
        items = row["items"]
        if not isinstance(items, list) or not items:
            raise ValueError()
        parsed = []
        for item in items:
            if type(item["quantity"]) is not int or item["quantity"] <= 0 or not item["reason"] or not item["movement_id"]:
                raise ValueError()
            if not isinstance(item["product_code"], str) or not item["product_code"].strip():
                raise ValueError()
            if not isinstance(item["reason"], str) or not item["reason"].strip():
                raise ValueError()
            parsed.append(SupplierReturnItem(str(UUID(str(item["id"]))), item["product_code"],
                str(item.get("product_name") or ""), item["quantity"], item["reason"], str(UUID(str(item["movement_id"])))))
        if not row["created_by"] or not row["created_on"]:
            raise ValueError()
        return SupplierReturn(str(UUID(str(row["id"]))), str(UUID(str(row["company_id"]))), str(UUID(str(row["supplier_id"]))),
            str(row.get("supplier_name") or ""), str(UUID(str(row["purchase_id"]))) if row.get("purchase_id") else None,
            str(UUID(str(row["created_by"]))), str(row["created_on"]), str(UUID(str(row["idempotency_key"]))), tuple(parsed),
            str(row.get("created_by_name") or ""))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RuntimeError("Resposta inválida da devolução. Consulte o histórico antes de repetir.") from None


class SupabaseSupplierReturnRepository:
    def __init__(self, client, company_id, role=None):
        self.client = client
        self.company_id = str(company_id)
        self.role = role

    def _rpc(self, function, args):
        try:
            return self.client.rpc(function, args).execute().data
        except Exception as error:
            if _e_recusa_de_permissao(error):
                raise PermissionDeniedError("operar devoluções ao fornecedor", self.role) from error
            if str(getattr(error, "code", "")) in {"23514", "23503", "22023"}:
                raise ValueError(getattr(error, "message", None) or str(error)) from None
            raise

    def create(self, data):
        row = self._rpc("fn_register_supplier_return", {
            "p_company_id": self.company_id, "p_supplier_id": str(UUID(data.supplier_id)),
            "p_purchase_id": str(UUID(data.purchase_id)) if data.purchase_id else None,
            "p_items": [{"product_code": item.product_code, "quantity": item.quantity, "reason": item.reason} for item in data.items],
            "p_idempotency_key": data.idempotency_key,
        })
        return parse_supplier_return(row)

    def get(self, return_id):
        return parse_supplier_return(self._rpc("fn_get_supplier_return", {
            "p_company_id": self.company_id, "p_id": str(UUID(return_id)),
        }))

    def list_all(self, *, supplier_id=None, purchase_id=None, limit=50, offset=0):
        rows = self._rpc("fn_list_supplier_returns", {"p_company_id": self.company_id,
            "p_supplier_id": str(UUID(supplier_id)) if supplier_id else None,
            "p_purchase_id": str(UUID(purchase_id)) if purchase_id else None,
            "p_limit": limit, "p_offset": offset})
        if not isinstance(rows, list):
            raise RuntimeError("Resposta inválida da consulta de devoluções.")
        return tuple(parse_supplier_return(row) for row in rows)
