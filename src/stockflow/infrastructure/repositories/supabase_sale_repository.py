from decimal import Decimal

from stockflow.infrastructure.repositories.demo_sale_repository import (
    resumo_dos_itens,
    sale_row,
)
from stockflow.infrastructure.fiscal.nfe_client import NFeClient


def _receipt_row(receipt):
    itens = receipt.get("sale_items") or []
    codigo, descricao = resumo_dos_itens(itens)
    row = sale_row(receipt["id"], receipt["client_name"], codigo, descricao,
                   Decimal(str(receipt["total"])), receipt["created_on"],
                   item_count=len(itens))
    row.update(payment_method=receipt.get("payment_method"),
               discount=str(receipt.get("discount", 0)),
               status=receipt.get("status", "CONCLUIDA"), items=itens)
    return row


class SupabaseSaleRepository:
    def __init__(self, client, company_id):
        self._client, self._company_id = client, company_id

    @staticmethod
    def _rows(response):
        return getattr(response, "data", None) or []

    def list_all(self):
        rows = (
            self._client.table("sales")
            .select(
                "id,client_name,total,created_on,"
                "sale_items(product_name,product_code,quantity)"
            )
            .eq("company_id", self._company_id)
            .order("created_on", desc=True)
            .execute()
            .data
            or []
        )
        vendas = []
        for r in rows:
            codigo, descricao = resumo_dos_itens(r.get("sale_items") or [])
            vendas.append(
                sale_row(
                    r["id"],
                    r["client_name"],
                    codigo,
                    descricao,
                    Decimal(str(r["total"])),
                    r["created_on"],
                )
            )
        return vendas

    def register(self, client, product, total):
        rows = (
            self._client.table("products")
            .select("id,ncm")
            .eq("company_id", self._company_id)
            .eq("barcode", product.code)
            .execute()
            .data
            or []
        )
        if not rows:
            raise ValueError("Produto não encontrado nesta empresa.")

        sale_id = (
            self._client.rpc(
                "fn_register_sale",
                {
                    "p_company_id": self._company_id,
                    "p_client_id": client.client_id,
                    "p_product_id": rows[0]["id"],
                    "p_total": str(total),
                },
            )
            .execute()
            .data
        )

        # --- EMISSÃO FISCAL: VENDA CONCLUÍDA ---
        fiscal = NFeClient()
        fiscal.emitir_nota(
            "VENDA",
            {
                "sale_id": str(sale_id),
                "client_name": client.name,
                "client_document": getattr(client, "document", ""),
                "product_code": product.code,
                "product_name": product.name,
                "ncm": rows[0].get("ncm", ""),
                "total": float(total),
            },
        )

        return sale_row(sale_id, client.name, product.code, product.name, total, "Hoje")

    def register_items(self, client, itens, payment_method, discount, total):
        """Venda com vários itens (US10).

        O preço unitário NÃO é enviado: `fn_create_complete_sale` lê
        `products.sell_price` no banco. Mandá-lo daqui deixaria o cliente
        escolher por quanto vende.
        """
        codigos = [i["product"].code for i in itens]
        achados = (
            self._client.table("products")
            .select("id,barcode")
            .eq("company_id", self._company_id)
            .in_("barcode", codigos)
            .execute()
            .data
            or []
        )
        por_codigo = {r["barcode"]: r["id"] for r in achados}

        faltando = [c for c in codigos if c not in por_codigo]
        if faltando:
            raise ValueError(
                "Produto não encontrado nesta empresa: " + ", ".join(faltando)
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
        receipt = self._client.rpc("fn_register_sale", {
            "p_company_id": self._company_id,
            "p_client_id": client.client_id,
            "p_items": payload,
            "p_payment_method": payment_method,
            "p_discount": str(discount),
        }).execute().data
        if not isinstance(receipt, dict) or not isinstance(receipt.get("items"), list):
            raise RuntimeError("O banco retornou um registro de venda inválido.")
        items = receipt["items"]
        codes, description = resumo_dos_itens(items)
        row = sale_row(
            receipt["id"],
            receipt["cliente"],
            codes,
            description,
            Decimal(str(receipt["total"])),
            receipt["created_on"],
            item_count=len(items),
        )
        row.update(
            payment_method=payment_method,
            discount=str(discount),
            status="CONCLUIDA",
            items=items,
        )
        return row

    def register_items(self, client, itens, payment_method, discount, total):
        from stockflow.application.dto.sale_item import SaleItemInput

        items = tuple(
            SaleItemInput(item["product"].code, item["quantity"])
            for item in itens
        )
        return self.register_multiple(
            client, items, total, payment_method, discount
        )
