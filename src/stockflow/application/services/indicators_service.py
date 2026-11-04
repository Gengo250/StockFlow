"""Caso de uso de consulta dos indicadores de vendas e estoque (US16)."""

from datetime import date

from stockflow.application.dto.sale_filter import TAMANHO_MAXIMO, SaleFilter
from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.domain.permissions import ensure_can_view_indicators
from stockflow.domain.sales_indicators import (
    LowStockProduct,
    SalesIndicators,
    low_stock_products,
    summarize_sales,
)


class IndicatorsService:
    """Lê o histórico já existente e o resume; não grava nada.

    Recebe o `SaleService` e não o repositório de vendas: a paginação, a
    validação de tamanho de página e o escopo de empresa já têm dono ali, e
    duplicá-los aqui criaria um segundo caminho de consulta ao histórico que
    poderia divergir do que a tela de Vendas mostra.

    A permissão é conferida ANTES de qualquer leitura, como em
    `PriceHistoryService.list_changes`: quem não pode ver os indicadores
    também não gasta a consulta que os produziria.
    """

    #: A única situação que é venda confirmada. `PENDENTE` é carrinho em
    #: montagem; `CANCELADA` e `DEVOLVIDA` são vendas desfeitas. Filtrar por
    #: este valor é o que mantém as três fora do faturamento, da contagem e
    #: do ranking — pelo filtro da consulta, não por descarte posterior.
    SITUACAO_CONFIRMADA = SaleStatus.CONCLUIDA.value

    def __init__(self, sale_service, products):
        self._sales = sale_service
        # Atributo, e não chamada direta ao repositório: no modo banco a
        # janela troca esta leitura por `list_snapshot`, que consulta sem
        # reescrever o catálogo compartilhado pelas telas. É o mesmo ponto de
        # troca que `DashboardPage.read_products` já usa.
        self.read_products = products.list_all

    def commercial(
        self, session, date_from: date | None = None, date_to: date | None = None
    ) -> SalesIndicators:
        """Faturamento, quantidade, ticket médio e ranking do período.

        `date_to` é INCLUSIVO, como em toda a aplicação: quem converte para
        o limite exclusivo do banco é o adaptador, num lugar só.
        """
        ensure_can_view_indicators(session, "consultar os indicadores de vendas")
        # `SaleFilter` recusa período invertido no próprio construtor. Montar
        # o filtro antes da primeira consulta é o que transforma essa recusa
        # em erro de domínio em vez de uma ida inútil à rede.
        filtro = SaleFilter(
            date_from=date_from,
            date_to=date_to,
            status=self.SITUACAO_CONFIRMADA,
            sort="DATA_DESC",
        )
        return summarize_sales(self._todas_as_linhas(session, filtro))

    def _todas_as_linhas(self, session, filtro) -> list:
        """Todas as vendas do recorte, página cheia por página cheia.

        `fn_list_sales` tem teto de 200 linhas por chamada e o avisa com uma
        exceção, não truncando em silêncio. Parar na primeira página daria um
        faturamento menor que o real justamente nos períodos movimentados,
        que são os que alguém consulta.
        """
        linhas = []
        pagina = 1
        while True:
            resultado = self._sales.list_sales(
                session, filtro, pagina, TAMANHO_MAXIMO
            )
            linhas.extend(resultado.rows)
            if not resultado.rows or pagina >= resultado.pages:
                return linhas
            pagina += 1

    def low_stock(self, session) -> tuple[LowStockProduct, ...]:
        """Produtos ativos em ou abaixo do mínimo, pelo saldo de AGORA.

        Não recebe período de propósito: a US16 pede a situação atual do
        estoque, e reconstruir o saldo que cada produto tinha no fim de um
        período passado exigiria somar o histórico de movimentações — outra
        história, não esta.
        """
        ensure_can_view_indicators(session, "consultar o estoque baixo")
        return low_stock_products(self.read_products())
