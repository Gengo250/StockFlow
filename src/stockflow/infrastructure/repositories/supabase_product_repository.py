"""Adaptador de `ProductRepository` sobre o Supabase.

Mesma porta do `DemoProductRepository`, então o `ProductService` e tudo acima
dele não sabem qual dos dois está em uso — a troca é de uma linha na
`MainWindow`.

DUAS REGRAS QUE ESTE ARQUIVO NÃO IMPLEMENTA, DE PROPÓSITO:

1. Permissão. Quem recusa é `fn_has_role` dentro de cada função
   `SECURITY DEFINER`, e antes dela o `ProductService`. Repetir a checagem
   aqui criaria uma terceira cópia da mesma regra, e a cópia que esquecesse
   de ser atualizada seria a que vale para quem chamar por este caminho.
2. Escopo de empresa na LEITURA. As consultas filtram por `company_id` para
   não trafegar o que não interessa, mas o que garante o isolamento é a RLS
   (`products_select` com `fn_is_member`). Um `company_id` errado aqui
   devolve vazio, não dado de outra empresa.

TODA ESCRITA PASSA POR RPC. As tabelas não têm GRANT de INSERT/UPDATE para
nenhuma role de aplicação — só SELECT. Gravar é chamar `fn_create_products`,
`fn_update_products`, `fn_set_product_active` e `fn_set_min_stock`.
"""

import dataclasses

from stockflow.application.dto.product_input import ProductInput
from stockflow.domain.enums.product_unit import PRODUCT_UNITS
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.stock_level import (
    derive_stock_status,
    to_int,
    to_min,
)
from stockflow.infrastructure.repositories.demo_product_repository import (
    next_product_code,
)
from stockflow.presentation.demo_products import Product
from stockflow.infrastructure.repositories.product_mapper import (
    product_input_to_create_args,
    product_input_to_update_args,
    row_to_product,
)

# Trechos que identificam uma recusa de autorização vinda do banco. O
# PostgREST entrega a exceção do Postgres como mensagem; o código SQLSTATE
# `42501` (insufficient_privilege) é o sinal confiável, e os textos cobrem as
# mensagens que as funções do catálogo levantam explicitamente.
PERMISSION_SQLSTATE = "42501"
PERMISSION_HINTS = (
    "sem permissão",
    "não encontrado ou sem permissão",
    "permission denied",
)

# Nome da função -> ação em português, para a mensagem de recusa. O rótulo é o
# MESMO que `ProductService` usa ao chamar `ensure_can_manage_products`: quando
# o banco recusa algo que a aplicação deixou passar, as duas mensagens
# coincidem e a divergência fica visível em vez de parecer outro erro.
ACTION_BY_RPC = {
    "fn_create_products": "cadastrar produtos",
    "fn_update_products": "editar produtos",
    "fn_set_product_active": "ativar ou desativar produtos",
    "fn_set_min_stock": "configurar o estoque mínimo",
}


class SupabaseProductRepository:
    def __init__(self, client, company_id, role=None):
        self._client = client
        self._company_id = company_id
        # Só para nomear o papel na mensagem de recusa. NÃO é usado para
        # decidir nada: a decisão é do `ProductService` antes e do
        # `fn_has_role` depois.
        self._role = role
        # Cache de `barcode -> id`. A tela trabalha com o código e as funções
        # de escrita exigem o uuid, então sem isto toda gravação gastaria uma
        # consulta extra só para traduzir. É preenchido pelas leituras e
        # invalidado pelas escritas que podem mudar o código.
        self._ids = {}

        # A FOTO que as telas leem. `DemoProductRepository` recebe esse dict
        # pronto e grava DENTRO dele — é essa identidade que faz uma gravação
        # aparecer na tabela. Aqui o dict nasce na primeira `load_catalog` e
        # passa a ser mantido pelas escritas, para que os dois adaptadores
        # tenham o mesmo comportamento observável sem mudar a porta.
        #
        # Sem isto, gravar ia ao banco e a tela continuava mostrando o valor
        # velho até reiniciar a aplicação.
        self._catalog = None

    # ======================================================
    # LEITURA
    # ======================================================

    def _products_query(self):
        return (
            self._client.table("products")
            .select("id,barcode,name,sell_price,buy_price,unit,stock,item_category,active")
            .eq("company_id", self._company_id)
        )

    @staticmethod
    def _rows(response):
        """Linhas da resposta, tolerando resposta vazia.

        O cliente devolve `data = None` em algumas condições de erro já
        tratadas no servidor; iterar sobre `None` quebraria a montagem da
        tela por um caso que significa apenas "nada veio".
        """
        return getattr(response, "data", None) or []

    def _category_names(self) -> dict:
        """`id -> nome` das categorias da empresa."""
        response = (
            self._client.table("categories")
            .select("id,name")
            .eq("company_id", self._company_id)
            .execute()
        )
        return {row["id"]: row["name"] for row in self._rows(response)}

    def _minimums(self, product_ids) -> dict:
        """`product_id -> min_quantity`, em UMA consulta.

        Em lote, e não por produto: `product_stock` tem uma linha por produto
        e consultar dentro do laço de montagem do catálogo seria N+1 — com 300
        produtos, 300 idas à rede para abrir a tela de Estoque.
        """
        if not product_ids:
            return {}
        response = (
            self._client.table("product_stock")
            .select("product_id,min_quantity")
            .in_("product_id", list(product_ids))
            .execute()
        )
        return {row["product_id"]: row["min_quantity"] for row in self._rows(response)}

    def load_catalog(self) -> dict:
        """Catálogo inteiro como o dict `code -> Product` que as telas usam.

        Três consultas em vez de um join: a FK de categoria é composta
        (`company_id`, `item_category`), e a detecção de relacionamento do
        PostgREST não a resolve de forma confiável. Montar o vínculo aqui é
        explícito e não depende dessa inferência.
        """
        rows = self._rows(self._products_query().order("created_on").execute())
        categorias = self._category_names()
        minimos = self._minimums([row["id"] for row in rows])

        catalogo = {}
        self._ids = {}
        for row in rows:
            produto = row_to_product(
                row,
                category_name=categorias.get(row.get("item_category")),
                minimum_stock=minimos.get(row["id"]),
            )
            catalogo[produto.code] = produto
            self._ids[produto.code] = row["id"]

        # Preenche NO LUGAR a partir da segunda chamada. Devolver um dict novo
        # toda vez desligaria as telas da foto: elas guardam a referência que
        # receberam na montagem, e `list_all` chama este método — sem o
        # preenchimento in-place, uma simples listagem trocaria a foto por um
        # dict órfão e a tela congelaria de novo, em silêncio.
        if self._catalog is None:
            self._catalog = catalogo
        else:
            self._catalog.clear()
            self._catalog.update(catalogo)
        return self._catalog

    def list_all(self):
        """Catálogo na ordem de cadastro, ativos e inativos."""
        return tuple(self.load_catalog().values())

    def get(self, code: str):
        """Produto pelo código, ou `None`. Não filtra por situação.

        O inativo continua sendo devolvido: quem decide se ele serve para a
        operação é a política da US02, e a consulta de operações antigas
        depende justamente de ainda alcançá-lo.
        """
        rows = self._rows(self._products_query().eq("barcode", code).limit(1).execute())
        if not rows:
            return None
        row = rows[0]
        self._ids[code] = row["id"]
        categorias = self._category_names()
        minimos = self._minimums([row["id"]])
        return row_to_product(
            row,
            category_name=categorias.get(row.get("item_category")),
            minimum_stock=minimos.get(row["id"]),
        )

    def exists(self, code: str) -> bool:
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
        return bool(rows)

    def _product_id(self, code: str):
        """uuid do produto, consultando só quando o cache não tem."""
        if code not in self._ids:
            self.exists(code)
        return self._ids.get(code)

    def list_active_categories(self) -> tuple[str, ...]:
        return tuple(sorted(self._category_names().values()))

    def is_category_active(self, category: str) -> bool:
        """A categoria existe NESTA empresa.

        `categories` não tem coluna `active`: existir na empresa é o que
        `fn_create_products` exige, e inventar aqui um conceito de categoria
        inativa recusaria cadastro que o banco aceitaria.
        """
        return category in set(self._category_names().values())

    def list_active_units(self) -> tuple[str, ...]:
        """Unidades do enum `public.unit_enum`, na ordem da UI.

        Lista estática porque o conjunto é um TIPO do banco, não uma tabela:
        só muda com migration, e consultá-la a cada abertura de formulário
        custaria uma ida à rede para um valor que não varia em runtime.
        """
        return tuple(PRODUCT_UNITS)

    def is_unit_active(self, unit: str) -> bool:
        return unit in set(PRODUCT_UNITS)

    def next_code(self) -> str:
        """Próximo código livre, derivado dos que já existem na empresa."""
        rows = self._rows(
            self._client.table("products")
            .select("barcode")
            .eq("company_id", self._company_id)
            .execute()
        )
        return next_product_code([row["barcode"] for row in rows if row.get("barcode")])

    # ======================================================
    # ESCRITA
    # ======================================================

    def create(self, data: ProductInput) -> str:
        product_id = self._rpc(
            "fn_create_products", product_input_to_create_args(data, self._company_id)
        )
        self._ids[data.code] = product_id
        self._aplicar_minimo(product_id, data)
        # `fn_create_products` não recebe `active`: a coluna nasce `true`.
        # Só vale uma chamada extra quando o formulário pediu inativo.
        if not data.active:
            self._rpc(
                "fn_set_product_active",
                {"p_product_id": product_id, "p_active": False},
            )
        self._publicar(data.code, data)
        return data.code

    def update(self, code: str, data: ProductInput) -> str:
        product_id = self._product_id(code)
        if product_id is None:
            raise LookupError(f"Produto {code} não encontrado.")

        self._rpc("fn_update_products", product_input_to_update_args(data, product_id))
        self._aplicar_minimo(product_id, data)
        # Situação de cadastro tem função própria; ver a nota em
        # `product_input_to_update_args`.
        self._rpc(
            "fn_set_product_active",
            {"p_product_id": product_id, "p_active": bool(data.active)},
        )

        # O código é somente leitura na tela, mas se deixar de ser, a chave do
        # cache precisa acompanhar — senão a próxima gravação resolveria o
        # uuid pelo código antigo.
        if data.code != code:
            self._ids.pop(code, None)
            self._ids[data.code] = product_id
        self._publicar(data.code, data, remover=code)
        return data.code

    def set_active(self, code: str, active: bool) -> None:
        """Ativar/desativar sem passar pelo formulário (US02/US04).

        Existe porque a tabela de Estoque alterna a situação direto na linha.
        `fn_set_product_active` é soft-delete: a linha continua no banco, e é
        isso que mantém o histórico de vendas resolvendo a chave estrangeira.
        """
        product_id = self._product_id(code)
        if product_id is None:
            raise LookupError(f"Produto {code} não encontrado.")
        self._rpc(
            "fn_set_product_active",
            {"p_product_id": product_id, "p_active": bool(active)},
        )

        # Aqui a foto é corrigida por `replace`, não remontada: o chamador só
        # informou a situação de cadastro, e reconstruir o produto a partir
        # disso apagaria nome, preço e saldo.
        if self._catalog is not None and code in self._catalog:
            self._catalog[code] = dataclasses.replace(
                self._catalog[code], active=bool(active)
            )

    def _publicar(self, code: str, data, remover: str = None) -> None:
        """Reflete na foto compartilhada o que acabou de ser gravado.

        Write-through OTIMISTA: monta o `Product` a partir do que foi enviado,
        sem reler do banco. Reconsultar custaria três requisições por gravação
        (produtos, categorias e mínimos), desfazendo no caminho de escrita o
        cuidado que `_minimums` tomou contra N+1 no de leitura.

        O risco assumido é a foto refletir "o que eu mandei" em vez de "o que
        o banco guardou". É pequeno porque `fn_update_products` grava as
        colunas como vieram; se algum dia passar a derivar valor, este é o
        ponto que precisa virar releitura.

        Silencioso quando ainda não há foto: há chamadores que gravam sem
        nunca ter listado o catálogo, e levantar aqui transformaria gravação
        válida em erro.
        """
        if self._catalog is None:
            return
        if remover and remover != code:
            self._catalog.pop(remover, None)
        self._catalog[code] = self._to_product(data)

    def _to_product(self, data) -> Product:
        """`ProductInput` -> `Product`, o modelo de leitura das telas.

        Mesma tradução de `DemoProductRepository._to_product`: a situação de
        estoque é DERIVADA do saldo contra o mínimo, nunca copiada.
        """
        estoque = to_int(data.stock)
        minimo = getattr(data, "minimum_stock", None)
        return Product(
            code=data.code,
            name=data.name,
            category=data.category,
            unit=data.unit,
            sale_price=data.sale_price,
            cost=data.cost,
            active=bool(data.active),
            stock=str(estoque),
            stock_status=derive_stock_status(estoque, minimo),
            minimum_stock=to_min(minimo),
        )

    def _aplicar_minimo(self, product_id, data) -> None:
        """Grava o estoque mínimo, que mora em `product_stock`, não em `products`."""
        # `None` é propagado como NULL, que é como `fn_set_min_stock` LIMPA
        # o mínimo. A versão anterior substituía a ausência por 10 e gravava
        # no banco um limiar que ninguém configurou — o produto passava a
        # alertar por decisão do adaptador.
        self._rpc(
            "fn_set_min_stock",
            {"p_product_id": product_id,
             "p_min": to_min(getattr(data, "minimum_stock", None))},
        )

    def _rpc(self, name: str, args: dict):
        """Chama a função e traduz recusa de autorização para o erro de domínio.

        Sem esta tradução, uma recusa do banco chegaria à `MainWindow` como
        exceção crua do cliente HTTP e cairia fora dos `except
        PermissionDeniedError` que a US01 instalou — a tela mostraria um
        traceback em vez da mensagem de permissão.
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


def _mensagem(erro) -> str:
    return getattr(erro, "message", None) or str(erro)


def _e_recusa_de_permissao(erro) -> bool:
    if str(getattr(erro, "code", "")) == PERMISSION_SQLSTATE:
        return True
    texto = _mensagem(erro).casefold()
    return any(trecho in texto for trecho in PERMISSION_HINTS)
