from decimal import Decimal

from stockflow.infrastructure.repositories.demo_sale_repository import (
    resumo_dos_itens,
    sale_row,
)


class SupabaseSaleRepository:
    def __init__(self, client, company_id):
        self._client, self._company_id = client, company_id

    @staticmethod
    def _rows(response):
        return getattr(response, "data", None) or []

    def list_all(self):
        sales = self._rows(
            self._client.table("sales")
            .select("id,client_name,total,created_on,status,payment_method,discount")
            .eq("company_id", self._company_id)
            .order("created_on", desc=True)
            .execute()
        )
        if not sales:
            return []
        sale_ids = [row["id"] for row in sales]
        item_rows = self._rows(
            self._client.table("sale_items")
            .select("sale_id,product_code,product_name,quantity,created_on")
            .in_("sale_id", sale_ids)
            .order("created_on")
            .order("id")
            .execute()
        )
        items_by_sale = {}
        for item in item_rows:
            items_by_sale.setdefault(item["sale_id"], []).append(item)

        result = []
        for sale in sales:
            items = items_by_sale.get(sale["id"], [])
            codes, description = resumo_dos_itens(items)
            row = sale_row(
                sale["id"], sale["client_name"], codes, description,
                Decimal(str(sale["total"])), sale["created_on"],
                item_count=len(items),
            )
            row.update({
                "status": sale["status"],
                "payment_method": sale["payment_method"],
                "discount": str(sale["discount"]),
            })
            result.append(row)
        return result

    def register(self, client, product, total):
        rows = self._rows(
            self._client.table("products")
            .select("id")
            .eq("company_id", self._company_id)
            .eq("barcode", product.code)
            .execute()
        )
        if not rows:
            raise ValueError("Produto não encontrado nesta empresa.")
        sale_id = self._client.rpc("fn_register_sale", {
            "p_company_id": self._company_id,
            "p_client_id": client.client_id,
            "p_product_id": rows[0]["id"],
            "p_total": str(total),
        }).execute().data
        return sale_row(
            sale_id, client.name, product.code, product.name, total, "Hoje",
            item_count=1,
        )

    def register_multiple(
        self,
        client,
        items,
        _total,
        payment_method="DINHEIRO",
        discount=Decimal("0"),
    ):
        payload = [
            {"product_code": item.product_code, "quantity": item.quantity}
            for item in items
        ]
        saved = self._client.rpc("fn_register_sale", {
            "p_company_id": self._company_id,
            "p_client_id": client.client_id,
            "p_items": payload,
            "p_payment_method": payment_method,
            "p_discount": str(discount),
        }).execute().data
        if not isinstance(saved, dict) or not isinstance(saved.get("items"), list):
            raise RuntimeError("O banco retornou um registro de venda inválido.")
        codes, description = resumo_dos_itens(saved["items"])
        return sale_row(
            saved["id"], saved["cliente"], codes, description,
            Decimal(str(saved["total"])), saved["created_on"],
            item_count=len(saved["items"]),
        )

    def register_items(self, client, itens, payment_method, discount, total):
        from stockflow.application.dto.sale_item import SaleItemInput

        items = tuple(
            SaleItemInput(item["product"].code, item["quantity"])
            for item in itens
        )
        return self.register_multiple(
            client, items, total, payment_method, discount
        )
