from decimal import Decimal

from stockflow.infrastructure.repositories.demo_sale_repository import sale_row


class SupabaseSaleRepository:
    def __init__(self, client, company_id):
        self._client, self._company_id = client, company_id

    @staticmethod
    def _rows(response):
        return getattr(response, "data", None) or []

    def list_all(self):
        sales = self._rows(
            self._client.table("sales")
            .select("id,client_name,product_code,product_name,total,created_on")
            .eq("company_id", self._company_id)
            .order("created_on", desc=True)
            .execute()
        )
        if not sales:
            return []
        sale_ids = [row["id"] for row in sales]
        item_rows = self._rows(
            self._client.table("sale_items")
            .select("sale_id,product_code,product_name,line_number")
            .in_("sale_id", sale_ids)
            .order("line_number")
            .execute()
        )
        items_by_sale = {}
        for item in item_rows:
            items_by_sale.setdefault(item["sale_id"], []).append(item)

        result = []
        for sale in sales:
            items = items_by_sale.get(sale["id"])
            if items:
                codes = [item["product_code"] for item in items]
                names = [item["product_name"] for item in items]
            else:
                codes = [sale["product_code"]]
                names = [sale["product_name"]]
            result.append(sale_row(
                sale["id"], sale["client_name"], codes, names,
                Decimal(str(sale["total"])), sale["created_on"],
            ))
        return result

    def register_multiple(self, client, items, _total):
        payload = [
            {"product_code": item.product_code, "quantity": item.quantity}
            for item in items
        ]
        saved = self._client.rpc("fn_register_sale", {
            "p_company_id": self._company_id,
            "p_client_id": client.client_id,
            "p_items": payload,
        }).execute().data
        if not isinstance(saved, dict) or not isinstance(saved.get("items"), list):
            raise RuntimeError("O banco retornou um registro de venda inválido.")
        codes = [item["product_code"] for item in saved["items"]]
        names = [item["product_name"] for item in saved["items"]]
        return sale_row(
            saved["id"], saved["cliente"], codes, names,
            Decimal(str(saved["total"])), saved["created_on"],
        )
