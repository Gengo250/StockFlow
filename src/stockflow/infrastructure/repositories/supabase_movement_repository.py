"""Adaptador de `MovementRepository` sobre o Supabase.

Mesma porta do `DemoMovementRepository`, e o mesmo desenho do
`SupabaseProductRepository` — inclusive no que ele deliberadamente NÃO faz:

1. **Permissão não é decidida aqui.** Quem recusa é `fn_has_role` dentro de
   cada função `SECURITY DEFINER`, e antes dela o `MovementService`. Uma
   terceira cópia da regra seria a que ficaria desatualizada.
2. **Escopo de empresa na leitura é da RLS.** A consulta filtra por
   `company_id` para não trafegar o que não interessa, mas o isolamento vem
   da policy com `fn_is_member`. Um `company_id` errado devolve vazio, não
   movimentação de outra empresa.

TODA ESCRITA PASSA POR RPC. `stock_movements` só tem GRANT de SELECT: gravar
é chamar `fn_register_movement`, `fn_confirm_movement` e `fn_cancel_movement`.
Isso não é só convenção — é o que garante que o trigger de saldo rode, que a
quantidade seja validada e que `created_by` venha da sessão.

CÓDIGO VERSUS UUID, nas duas direções:

- **escrevendo**, a tela entrega `product_code` (que é `products.barcode`) e
  a função exige `p_product_id uuid`. A tradução é a mesma de
  `SupabaseProductRepository`: cache `barcode -> id` alimentado por uma
  consulta escopada pela empresa.
- **lendo**, a linha traz `product_id` e a tela precisa de código e nome. A
  resolução é EM LOTE, uma consulta com `in_`, pelo motivo de sempre: por
  linha seria N+1, uma ida à rede por movimentação para abrir a tela.
"""

from stockflow.application.dto.movement_input import MovementInput
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.movement_mapper import (
    movement_input_to_register_args,
    rows_to_movements,
)
# Reusada, não copiada: a detecção de recusa (SQLSTATE 42501 + os trechos de
# mensagem) é a MESMA regra para as funções do catálogo e para as de
# movimentação. Duas cópias divergiriam na primeira mensagem nova, e a cópia
# esquecida deixaria passar uma recusa como erro cru na tela.
from stockflow.infrastructure.repositories.supabase_product_repository import (
    _e_recusa_de_permissao,
)

# Colunas que a tela consome. Lista explícita em vez de `*` para que uma
# coluna nova na tabela não comece a trafegar sozinha.
MOVEMENT_COLUMNS = "id,product_id,kind,quantity,status,note,created_on,confirmed_on"

# Nome da função -> ação em português. Os rótulos são os MESMOS que
# `MovementService` passa para `ensure_can_move_stock`: quando o banco recusa
# algo que a aplicação deixou passar, as duas mensagens coincidem e a
# divergência entre as camadas fica visível em vez de parecer outro erro.
ACTION_BY_RPC = {
    "fn_register_movement": "registrar movimentações",
    "fn_confirm_movement": "confirmar movimentações",
    "fn_cancel_movement": "cancelar movimentações",
}


class SupabaseMovementRepository:
    def __init__(self, client, company_id, role=None, agora=None):
        self._client = client
        self._company_id = company_id
        # Só para nomear o papel na mensagem de recusa. NÃO decide nada.
        self._role = role
        # Referência de "agora" para a coluna de data; ver `formatar_quando`.
        self._agora = agora
        # Cache `barcode -> id`, pelo mesmo motivo do adaptador de catálogo:
        # a tela trabalha com o código e as funções exigem o uuid, então sem
        # isto todo registro gastaria uma consulta extra só para traduzir.
        self._ids = {}

    # ======================================================
    # LEITURA
    # ======================================================

    @staticmethod
    def _rows(response):
        """Linhas da resposta, tolerando resposta vazia.

        O cliente devolve `data = None` em algumas condições já tratadas no
        servidor; iterar sobre `None` derrubaria a montagem da tela por um
        caso que significa apenas "nada veio".
        """
        return getattr(response, "data", None) or []

    def list_movements(self, product_code: str | None = None) -> tuple:
        """Movimentações da empresa, da mais recente para a mais antiga.

        Todas as situações, canceladas incluídas: esconder uma cancelada
        tiraria da tela a resposta para "por que o saldo mudou e voltou".
        """
        consulta = (
            self._client.table("stock_movements")
            .select(MOVEMENT_COLUMNS)
            .eq("company_id", self._company_id)
        )

        if product_code:
            product_id = self._product_id(product_code)
            # Código desconhecido NESTA empresa devolve vazio em vez de ir ao
            # banco sem o filtro: sem este desvio, um código errado traria o
            # histórico inteiro da empresa como se fosse o do produto.
            if product_id is None:
                return ()
            consulta = consulta.eq("product_id", product_id)

        # Ordenação ASCENDENTE no banco e inversão aqui. A ordem vem do
        # servidor porque é ele que tem o índice; a inversão é local porque a
        # forma do parâmetro de ordem decrescente mudou entre versões do
        # cliente PostgREST, e inverter uma lista já materializada custa um
        # passo sobre o que de qualquer modo será percorrido na montagem.
        linhas = list(self._rows(consulta.order("created_on").execute()))
        linhas.reverse()
        return rows_to_movements(linhas, self._produtos_das_linhas(linhas), self._agora)

    def _produtos_das_linhas(self, linhas) -> dict:
        """`product_id -> (código, nome)`, em UMA consulta.

        Em lote, e não por movimentação: um histórico de 300 linhas viraria
        300 idas à rede para abrir a tela. O conjunto dos ids também tira as
        repetições — várias movimentações do mesmo produto pesam uma vez só.
        """
        ids = {linha.get("product_id") for linha in linhas if linha.get("product_id")}
        if not ids:
            return {}
        resposta = (
            self._client.table("products")
            .select("id,barcode,name")
            .eq("company_id", self._company_id)
            .in_("id", list(ids))
            .execute()
        )
        produtos = {}
        for row in self._rows(resposta):
            codigo = row.get("barcode") or ""
            produtos[row["id"]] = (codigo, row.get("name") or "")
            # A leitura alimenta o cache de tradução, como em
            # `SupabaseProductRepository.load_catalog`: quem acabou de ver o
            # histórico de um produto costuma ser quem vai movimentá-lo.
            if codigo:
                self._ids[codigo] = row["id"]
        return produtos

    def _product_id(self, code: str):
        """uuid do produto, consultando só quando o cache não tem."""
        if code not in self._ids:
            rows = self._rows(
                self._client.table("products")
                .select("id")
                .eq("company_id", self._company_id)
                .eq("barcode", code)
                .limit(1)
                .execute()
            )
            if rows:
                self._ids[code] = rows[0]["id"]
        return self._ids.get(code)

    # ======================================================
    # ESCRITA
    # ======================================================

    def register(self, data: MovementInput) -> str:
        """Registra e devolve o uuid gerado pelo banco.

        O id vem do RETURNING da função, não de um valor inventado aqui:
        confirmar e cancelar o recebem de volta, e um identificador local não
        acharia linha nenhuma.
        """
        product_id = self._product_id(data.product_code)
        if product_id is None:
            # Antes da ida à rede, e com o CÓDIGO na mensagem: a função
            # responderia 'Produto não encontrado nesta empresa' falando de um
            # uuid que a tela nunca mostrou.
            raise LookupError(f"Produto {data.product_code} não encontrado.")
        return self._rpc(
            "fn_register_movement",
            movement_input_to_register_args(data, self._company_id, product_id),
        )

    def confirm(self, movement_id: str) -> None:
        """Confirma uma pendente. É esta transição que altera o saldo.

        Sem `company_id`: `fn_confirm_movement` resolve a empresa pela própria
        linha. Recebê-la do chamador deixaria confirmar movimentação de outra
        empresa bastando informar uma onde o usuário tem alçada — o mesmo
        buraco que `fn_update_products` fecha no catálogo.
        """
        self._rpc("fn_confirm_movement", {"p_movement_id": movement_id})

    def cancel(self, movement_id: str) -> None:
        """Cancela. Cancelar uma confirmada devolve o saldo (o trigger recalcula)."""
        self._rpc("fn_cancel_movement", {"p_movement_id": movement_id})

    def _rpc(self, name: str, args: dict):
        """Chama a função e traduz recusa de autorização para o erro de domínio.

        Sem esta tradução, uma recusa chegaria à tela como exceção crua do
        cliente HTTP e cairia fora dos `except PermissionDeniedError` que a
        aplicação instalou — apareceria um traceback onde deveria aparecer a
        mensagem de permissão.
        """
        try:
            response = self._client.rpc(name, args).execute()
        except Exception as erro:
            if _e_recusa_de_permissao(erro):
                raise PermissionDeniedError(
                    ACTION_BY_RPC.get(name, f"executar {name}"), self._role
                ) from erro
            raise
        return getattr(response, "data", None)
