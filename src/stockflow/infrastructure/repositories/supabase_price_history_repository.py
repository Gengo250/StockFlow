"""Histórico de preço e custo pelo Supabase (H09).

Tudo passa por `fn_list_price_edits`, e não por um SELECT em
`price_edit_log`: a linha guarda ids, a tela precisa de nomes, e o join
entre três tabelas não pertence à apresentação. A função também repete a
alçada de ADMIN que a policy já aplica — ler daqui e ler de lá dá a mesma
resposta.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from stockflow.domain.enums.price_edit_field import PriceEditField
from stockflow.domain.price_change import PriceChange


class SupabasePriceHistoryRepository:
    def __init__(self, client, company_id, products=None):
        self._client = client
        self._company_id = company_id
        # Cache `barcode -> id`, como nos adaptadores de catálogo e de
        # movimentação: a tela trabalha com o código e a função exige o uuid.
        self._products = products
        self._ids = {}

    def list_price_edits(self, product_code: str | None = None) -> tuple[PriceChange, ...]:
        product_id = None
        if product_code is not None:
            product_id = self._product_id(product_code)
            if product_id is None:
                # Filtro que não encontra o alvo devolve vazio. Mandar
                # `None` aqui transformaria "só este produto" em "a empresa
                # inteira" — a resposta mais errada possível para um filtro.
                return ()

        resposta = self._client.rpc(
            "fn_list_price_edits",
            {"p_company_id": self._company_id, "p_product_id": product_id},
        ).execute()

        # A ordem vem do `ORDER BY` da função. Reordenar aqui duplicaria a
        # regra em dois lugares, e o desempate pelo id não é reproduzível
        # fora do banco.
        return tuple(_para_mudanca(linha) for linha in (getattr(resposta, "data", None) or []))

    def _product_id(self, product_code: str):
        if product_code in self._ids:
            return self._ids[product_code]

        produto = None
        if self._products is not None:
            produto = self._products.get(product_code)
        if produto is None:
            linhas = (
                self._client.table("products")
                .select("id,barcode")
                .eq("company_id", self._company_id)
                .eq("barcode", product_code)
                .execute()
            )
            linhas = getattr(linhas, "data", None) or []
            produto_id = linhas[0]["id"] if linhas else None
        else:
            produto_id = getattr(produto, "id", None)

        self._ids[product_code] = produto_id
        return produto_id


def _para_mudanca(linha) -> PriceChange:
    return PriceChange(
        changed_on=_para_data(linha.get("changed_on")),
        product_code=linha.get("product_code") or "",
        product_name=linha.get("product_name") or "",
        field=PriceEditField.from_value(linha.get("field")),
        old_price=_para_decimal(linha.get("old_price")),
        new_price=_para_decimal(linha.get("new_price")),
        changed_by=linha.get("changed_by") or "",
    )


def _para_decimal(valor):
    """`None` continua `None`: é "antes não havia valor", e não zero.

    Esta é a metade da decisão que a coluna nullable de `price_edit_log`
    começou. Converter para `Decimal(0)` aqui reintroduziria na tela o custo
    inventado que o banco se recusa a gravar.
    """
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        return None


def _para_data(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
