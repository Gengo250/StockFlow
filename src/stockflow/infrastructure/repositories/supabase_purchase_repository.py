import json

from stockflow.application.dto.purchase_input import PurchaseInput
from stockflow.domain.enums.purchase_status import PurchaseStatus
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.purchase import Purchase, PurchaseItem
from stockflow.infrastructure.repositories.supabase_product_repository import (
    _e_recusa_de_permissao,
)


ACTION_BY_RPC = {
    "fn_create_purchase": "criar compras",
    "fn_list_company_purchases": "consultar compras",
    "fn_receive_purchase": "receber compras",
}


class SupabasePurchaseRepository:
    def __init__(self, client, company_id, role=None):
        self._client = client
        self._company_id = company_id
        self._role = role

    def list_all(self) -> tuple[Purchase, ...]:
        response = self._rpc(
            "fn_list_company_purchases", {"p_company_id": self._company_id}
        )
        return tuple(self._purchase(row) for row in (response or ()))

    def create(self, data: PurchaseInput) -> str:
        response = self._rpc(
            "fn_create_purchase",
            {
                "p_company_id": self._company_id,
                "p_supplier_id": data.supplier_id,
                "p_items": [
                    {"product_code": item.product_code, "quantity": item.quantity}
                    for item in data.items
                ],
            },
        )
        if not response:
            raise RuntimeError("O banco não retornou o identificador da compra criada.")
        return str(response)

    def receive(self, purchase_id: str) -> None:
        self._rpc("fn_receive_purchase", {"p_purchase_id": purchase_id})

    @staticmethod
    def _purchase(row) -> Purchase:
        items = row.get("items") or []
        if isinstance(items, str):
            items = json.loads(items)
        if not isinstance(items, list):
            raise ValueError("O banco retornou uma lista de itens de compra inválida.")
        return Purchase(
            purchase_id=str(row["id"]),
            supplier_id=str(row["supplier_id"]),
            supplier_name=str(row.get("supplier_name") or ""),
            status=PurchaseStatus.from_value(row["status"]),
            items=tuple(
                PurchaseItem(
                    product_code=str(item.get("product_code") or ""),
                    product_name=str(item.get("product_name") or ""),
                    quantity=int(item["quantity"]),
                )
                for item in items
            ),
            created_on=str(row.get("created_on") or ""),
            received_on=(
                str(row["received_on"]) if row.get("received_on") else None
            ),
        )

    def _rpc(self, name, args):
        try:
            response = self._client.rpc(name, args).execute()
        except Exception as error:
            if _e_recusa_de_permissao(error):
                raise PermissionDeniedError(
                    ACTION_BY_RPC[name], self._role
                ) from error
            raise
        return getattr(response, "data", None)
