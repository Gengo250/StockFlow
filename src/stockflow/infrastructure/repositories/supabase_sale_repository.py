from decimal import Decimal

from stockflow.infrastructure.repositories.demo_sale_repository import (
    resumo_dos_itens,
    sale_row,
)


class SupabaseSaleRepository:
    def __init__(self, client, company_id):
        self._client, self._company_id = client, company_id

    def list_all(self):
        # Os produtos vendidos moram em `sale_items` desde a US10. O embed do
        # PostgREST traz os itens junto com o cabeçalho: uma ida ao banco por
        # listagem, e não uma por venda.
        rows = (self._client.table("sales")
                .select("id,client_name,total,created_on,"
                        "sale_items(product_name,product_code,quantity)")
                .eq("company_id", self._company_id).order("created_on", desc=True)
                .execute().data or [])
        vendas = []
        for r in rows:
            codigo, descricao = resumo_dos_itens(r.get("sale_items") or [])
            vendas.append(sale_row(r["id"], r["client_name"], codigo, descricao,
                                   Decimal(str(r["total"])), r["created_on"]))
        return vendas

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

    def register_items(self, client, itens, payment_method, discount, total):
        """Venda com vários itens (US10).

        O preço unitário NÃO é enviado: `fn_create_complete_sale` lê
        `products.sell_price` no banco. Mandá-lo daqui deixaria o cliente
        escolher por quanto vende.
        """
        codigos = [i["product"].code for i in itens]
        achados = (self._client.table("products").select("id,barcode")
                   .eq("company_id", self._company_id).in_("barcode", codigos)
                   .execute().data or [])
        por_codigo = {r["barcode"]: r["id"] for r in achados}

        faltando = [c for c in codigos if c not in por_codigo]
        if faltando:
            raise ValueError(
                "Produto não encontrado nesta empresa: " + ", ".join(faltando)
            )

        payload = [
            {"product_id": por_codigo[i["product"].code], "quantity": int(i["quantity"])}
            for i in itens
        ]
        sale_id = self._client.rpc("fn_create_complete_sale", {
            "p_company_id": self._company_id,
            "p_client_id": client.client_id,
            "p_items": payload,
            "p_payment_method": payment_method,
            "p_discount": str(discount),
        }).execute().data

        codigo, descricao = resumo_dos_itens([
            {"product_name": i["product"].name, "product_code": i["product"].code,
             "quantity": i["quantity"]}
            for i in itens
        ])
        return sale_row(sale_id, client.name, codigo, descricao, total, "Hoje")
