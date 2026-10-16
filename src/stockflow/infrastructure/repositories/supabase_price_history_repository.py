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
        # `products` é aceito e IGNORADO de propósito. A tradução do código
        # para uuid não pode sair do repositório de catálogo: ele devolve
        # `Product`, que não carrega o uuid — e `getattr(produto, "id")`
        # respondia `None` para todo código, transformando "este produto" em
        # "nenhum produto" e abrindo a tela filtrada vazia.
        #
        # O argumento continua na assinatura porque `build_price_history_
        # repository` o passa para o adaptador de demonstração, que de fato
        # precisa dele.
        self._products = products
        # Cache `barcode -> id`, como nos adaptadores de catálogo e de
        # movimentação: a tela trabalha com o código e a função exige o uuid.
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

    def _product_id(self, code: str):
        """uuid do produto, consultando só quando o cache não tem.

        Guarda apenas o ACERTO. Cachear a ausência tornaria permanente uma
        resposta temporária: um produto que ainda não existia na primeira
        consulta continuaria sem histórico até a janela ser reaberta.
        """
        if code not in self._ids:
            linhas = (
                self._client.table("products")
                .select("id")
                .eq("company_id", self._company_id)
                .eq("barcode", code)
                .limit(1)
                .execute()
            )
            linhas = getattr(linhas, "data", None) or []
            if linhas:
                self._ids[code] = linhas[0]["id"]
        return self._ids.get(code)


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
