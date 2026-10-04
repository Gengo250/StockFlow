"""Porta de persistência de movimentações de estoque."""

from typing import Protocol

from stockflow.application.dto.movement_input import MovementInput


class MovementRepository(Protocol):
    """Contrato que a infraestrutura deve satisfazer.

    As quatro operações de escrita existem separadas porque são autorizações
    diferentes no banco e momentos diferentes no fluxo: registrar é uma
    intenção, confirmar é o que move o saldo, e cancelar desfaz.
    """

    def list_movements(self, product_code: str | None = None) -> tuple:
        """Movimentações da empresa, da mais recente para a mais antiga.

        Sem filtro traz todas; com `product_code`, só as do produto. Devolve
        TODAS as situações — esconder canceladas tiraria da tela a resposta
        para "por que o saldo mudou e voltou".
        """
        ...

    def register(self, data: MovementInput) -> str:
        """Registra e devolve o identificador. Nasce pendente salvo pedido."""
        ...

    def confirm(self, movement_id: str) -> None:
        """Confirma uma pendente. É esta transição que altera o saldo."""
        ...

    def cancel(self, movement_id: str) -> None:
        """Cancela. Cancelar uma confirmada devolve o saldo."""
        ...
