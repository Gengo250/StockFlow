from decimal import Decimal

from stockflow.infrastructure.repositories.demo_sale_repository import sale_row


class SupabaseSaleRepository:
    def __init__(self, client, company_id):
        self._client, self._company_id = client, company_id

    def list_all(self):
        rows = (self._client.table("sales")
                .select("id,client_name,product_code,product_name,total,created_on")
                .eq("company_id", self._company_id).order("created_on", desc=True)
                .execute().data or [])
        return [sale_row(r["id"], r["client_name"], r["product_code"],
                         r["product_name"], Decimal(str(r["total"])), r["created_on"])
                for r in rows]

    def register(self, client, product, total):
        rows = (self._client.table("products").select("id")
                .eq("company_id", self._company_id).eq("barcode", product.code)
                .execute().data or [])
        if not rows:
            raise ValueError("Produto não encontrado nesta empresa.")
        sale_id = self._client.rpc("fn_register_sale", {
            "p_company_id": self._company_id, "p_client_id": client.client_id,
            "p_product_id": rows[0]["id"], "p_total": str(total),
        }).execute().data
        return sale_row(sale_id, client.name, product.code, product.name, total, "Hoje")
