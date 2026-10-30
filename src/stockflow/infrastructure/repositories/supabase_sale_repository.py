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
               original_total=str(receipt.get("original_total", receipt.get("total", 0))),
               discount_applied_by=receipt.get("discount_applied_by"),
               discount_authorized_by=receipt.get("discount_authorized_by"),
               discount_authorized_by_name=receipt.get("discount_authorized_by_name", ""),
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
        original_total=str(linha.get("original_total", linha.get("total", 0))),
        discount_applied_by=linha.get("discount_applied_by"),
        discount_applied_by_name=linha.get("discount_applied_by_name", ""),
        discount_authorized_by=linha.get("discount_authorized_by"),
        discount_authorized_by_name=linha.get("discount_authorized_by_name", ""),
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
        *,
        original_total=None,
        sale_discount_type="FIXED",
        sale_discount_value=Decimal("0"),
        approval_credentials=None,
        seller_id=None,
    ):
        payload = [
            {
                "product_code": item.product_code,
                "quantity": item.quantity,
                "discount_type": item.discount_type,
                "discount_value": str(item.discount_value),
            }
            for item in items
        ]
        rpc_client = self._client
        temporary_client = None
        if approval_credentials:
            from stockflow.infrastructure.database.supabase_client import (
                create_independent_auth_client,
            )

            temporary_client = create_independent_auth_client()
            email, password = approval_credentials
            try:
                auth_result = temporary_client.auth.sign_in_with_password({
                    "email": email.strip(),
                    "password": password,
                })
            except Exception as error:
                raise ValueError("Credenciais de administrador inválidas.") from error
            if getattr(auth_result, "user", None) is None:
                raise ValueError("Credenciais de administrador inválidas.")

            approver_id = temporary_client.rpc(
                "fn_current_user_id", {}
            ).execute().data
            companies = temporary_client.rpc("fn_my_companies", {}).execute().data or []
            approver_company = next(
                (
                    row for row in companies
                    if str(row.get("company_id")) == str(self._company_id)
                ),
                None,
            )
            if not approver_id or not approver_company or approver_company.get(
                "user_role"
            ) != "ADMIN":
                raise ValueError(
                    "A aprovação exige um administrador ativo da mesma empresa."
                )
            rpc_client = temporary_client

        try:
            receipt = rpc_client.rpc("fn_register_sale_with_discounts", {
                "p_company_id": self._company_id,
                "p_client_id": client.client_id,
                "p_items": payload,
                "p_payment_method": payment_method,
                "p_sale_discount_type": sale_discount_type,
                "p_sale_discount_value": str(sale_discount_value),
                "p_seller_id": seller_id,
            }).execute().data
        except Exception as error:
            if (
                not approval_credentials
                and "aprovação de admin necessária" in str(error).casefold()
            ):
                from stockflow.application.services.sale_service import (
                    DiscountApprovalRequired,
                )

                raise DiscountApprovalRequired(
                    "Este desconto excede o limite do vendedor e exige "
                    "autorização de um administrador."
                ) from error
            raise
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
            discount=str(receipt.get("discount", discount)),
            original_total=str(receipt.get("original_total", original_total or "0")),
            status="CONCLUIDA",
            items=items,
            seller_id=receipt.get("seller_id", seller_id),
            discount_applied_by=receipt.get("discount_applied_by", seller_id),
            discount_authorized_by=receipt.get("discount_authorized_by"),
            discount_authorized_by_name=receipt.get(
                "discount_authorized_by_name", ""
            ),
        )
        return row

    def get_discount_limits(self):
        response = self._client.rpc(
            "fn_get_sale_discount_limits", {
                "p_company_id": self._company_id,
            }
        ).execute().data
        if not isinstance(response, dict) or "SELLER" not in response:
            raise RuntimeError("O banco retornou limites de desconto inválidos.")
        return {
            "SELLER": (
                None if response["SELLER"] is None
                else Decimal(str(response["SELLER"]))
            ),
            "ADMIN": None,
        }

    def set_discount_limits(self, limits):
        value = limits.get("SELLER")
        response = self._client.rpc("fn_set_sale_discount_limit", {
            "p_company_id": self._company_id,
            "p_role": "SELLER",
            "p_limit_percent": str(value),
        }).execute().data
        if response is None:
            raise RuntimeError("O banco não confirmou a atualização do limite.")
        return self.get_discount_limits()

    def register_items(self, client, itens, payment_method, discount, total):
        from stockflow.application.dto.sale_item import SaleItemInput

        items = tuple(
            SaleItemInput(item["product"].code, item["quantity"])
            for item in itens
        )
        return self.register_multiple(
            client, items, total, payment_method, discount
        )
