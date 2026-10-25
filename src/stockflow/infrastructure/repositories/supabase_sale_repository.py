from datetime import timedelta
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


def _history_row(linha):
    """Linha do histórico a partir do retorno de `fn_list_sales`.

    Irmã de `_receipt_row`, que monta o mesmo formato a partir do recibo da
    gravação. As duas existem porque as fontes diferem; o FORMATO não pode
    diferir, senão a tabela mostra uma coisa ao gravar e outra ao recarregar.
    """
    itens = linha.get("items") or []
    codigo, descricao = resumo_dos_itens(itens)
    row = sale_row(linha["id"], linha["client_name"], codigo, descricao,
                   Decimal(str(linha["total"])), linha["created_on"],
                   item_count=len(itens))
    row.update(
        payment_method=linha.get("payment_method"),
        discount=str(linha.get("discount", 0)),
        status=linha.get("status", "CONCLUIDA"),
        items=itens,
        client_id=linha.get("client_id"),
        seller_id=linha.get("seller_id"),
        seller=linha.get("seller_name") or "",
        reversal_kind=linha.get("reversal_kind"),
        reversal_reason=linha.get("reversal_reason"),
        reversal_on=linha.get("reversal_on"),
        reversal_by=linha.get("reversal_by_name") or "",
    )
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
                "id,client_name,total,created_on,payment_method,discount,status,"
                "sale_items(product_name,product_code,quantity,unit_price,subtotal)"
            )
            .eq("company_id", self._company_id)
            .order("created_on", desc=True)
            .execute()
            .data
            or []
        )
        return [_receipt_row(row) for row in rows]

    def list_page(self, filtro, page, size):
        """Uma página de `fn_list_sales`, com o total na mesma leitura."""
        from stockflow.application.dto.sale_filter import SalePage

        # O banco usa limite superior EXCLUSIVO; a tela pensa inclusivo. A
        # conversão mora aqui, num lugar só, para que este adaptador e o de
        # demonstração concordem sobre o que "até dia 5" significa.
        ate = filtro.date_to + timedelta(days=1) if filtro.date_to else None
        linhas = self._client.rpc("fn_list_sales", {
            "p_company_id": self._company_id,
            "p_sale_id": filtro.sale_id or None,
            "p_from": filtro.date_from.isoformat() if filtro.date_from else None,
            "p_to": ate.isoformat() if ate else None,
            "p_client_id": filtro.client_id or None,
            "p_seller_id": filtro.seller_id or None,
            "p_status": filtro.status or None,
            "p_sort": filtro.sort,
            "p_limit": size,
            "p_offset": (page - 1) * size,
        }).execute().data or []
        # `total_count` vem repetido em toda linha (`count(*) OVER ()`); sem
        # linha nenhuma o total é zero, e não "desconhecido".
        total = int(linhas[0]["total_count"]) if linhas else 0
        return SalePage(rows=tuple(_history_row(l) for l in linhas),
                        total=total, page=page, size=size)

    def get(self, sale_id):
        from stockflow.application.dto.sale_filter import SaleFilter

        pagina = self.list_page(SaleFilter(sale_id=str(sale_id)), 1, 1)
        return pagina.rows[0] if pagina.rows else None

    def cancel(self, sale_id, reason):
        return self._client.rpc("fn_cancel_sale", {
            "p_sale_id": str(sale_id), "p_reason": reason,
        }).execute().data

    def revert(self, sale_id, reason):
        return self._client.rpc("fn_return_sale", {
            "p_sale_id": str(sale_id), "p_reason": reason,
        }).execute().data

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
