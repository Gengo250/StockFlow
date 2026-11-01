"""Porta de persistência de vendas.

Vendas era o único domínio sem porta declarada. Enquanto o contrato foi
"grava e lista tudo", os dois adaptadores cabiam na cabeça. Com consulta
paginada, filtros e reversão (US17), o contrato precisa estar escrito num
lugar só — senão o repositório de demonstração e o do Supabase divergem em
silêncio, e os testes de interface passam a validar ficção.
"""

from typing import Protocol, TypedDict

from stockflow.application.dto.return_dto import ReturnResultDTO
from stockflow.application.dto.sale_filter import SaleFilter, SalePage


class ReturnItemPayload(TypedDict):
    sale_item_id: str
    quantity: int


class SaleRepository(Protocol):
    """Contrato que a infraestrutura deve satisfazer."""

    def list_page(self, filtro: SaleFilter, page: int, size: int) -> SalePage:
        """Uma página do histórico e o total que casa com o filtro.

        A ordem é a de `filtro.sort`, SEMPRE desempatada pelo identificador:
        sem desempate, duas vendas no mesmo instante trocam de lugar entre
        consultas e a página seguinte repete ou pula linha.
        """
        ...

    def get(self, sale_id: str) -> dict | None:
        """Uma venda com itens e vínculo de reversão, ou `None`.

        `None` e não exceção: a venda pode ter saído do alcance da empresa
        entre a listagem e o clique, e isso é informação para a tela, não
        falha.
        """
        ...

    def cancel(self, sale_id: str, reason: str) -> dict:
        """Anula a venda e devolve o saldo. Só para venda concluída."""
        ...

    def revert(self, sale_id: str, reason: str) -> dict:
        """Devolve a venda: entrada compensatória, saída original de pé."""
        ...

    def list_all(self) -> list:
        """Todo o histórico, sem paginar.

        Continua existindo para Dashboard e Relatórios, que AGREGAM em vez
        de listar. Não usar em tela de consulta: `max_rows` do PostgREST
        corta em 1000 linhas sem avisar, que é o defeito que `list_page`
        existe para resolver.
        """
        ...

    def get_returnable_items(self, sale_id: str) -> list[dict]:
        """Itens da venda concluída que ainda podem ser devolvidos."""
        ...

    def partial_return(
        self, sale_id: str, items: list[ReturnItemPayload], reason: str,
        idempotency_key: str,
    ) -> ReturnResultDTO:
        """Registra uma devolução parcial/total e restitui estoque atomicamente."""
        ...
