"""DTOs para criação de devolução (return)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Literal, TypedDict

from stockflow.domain.sale_return import return_identifier, return_money


@dataclass(frozen=True)
class ReturnItemDTO:
    """Item da devolução – identifica o item da venda e a quantidade a devolver."""

    sale_item_id: str
    quantity: int


@dataclass(frozen=True)
class CreateReturnDTO:
    """Payload para registrar devolução parcial.

    * ``sale_id`` – ID da venda original (já concluída).
    * ``items`` – lista de ``ReturnItemDTO``.
    * ``reason`` – motivo da devolução (texto livre, obrigatório).
    * ``idempotency_key`` – UUID criado antes do primeiro envio e reutilizado
      em tentativas da mesma operação. Ausência é rejeitada antes da escrita;
      nunca gerar outra chave automaticamente após uma resposta incerta.
    """

    sale_id: str
    items: List[ReturnItemDTO]
    reason: str
    # Compatibilidade de construção; o serviço rejeita ausência antes da escrita.
    idempotency_key: str = ""


class ReturnResultDTO(TypedDict):
    """Registro comercial/estoque concluído, sem promessa de emissão ou reembolso."""

    return_id: str
    status: Literal["COMPLETED"]
    total_amount: Decimal
    is_total_return: bool


def parse_return_result(value: object) -> ReturnResultDTO:
    """Contrato comum aos adaptadores; não preencher campos ausentes por omissão."""
    try:
        if not isinstance(value, dict) or value.get("status") != "COMPLETED":
            raise ValueError("Status de devolução inválido.")
        if type(value.get("is_total_return")) is not bool:
            raise ValueError("Indicador de devolução total inválido.")
        return ReturnResultDTO(
            return_id=return_identifier(value["return_id"]),
            status="COMPLETED",
            total_amount=return_money(value["total_amount"]),
            is_total_return=value["is_total_return"],
        )
    except (KeyError, ValueError, TypeError) as error:
        # O servidor pode ter feito COMMIT antes de devolver resposta incompatível.
        raise RuntimeError(
            "Resposta de devolução inválida. A operação pode ter sido registrada; "
            "não repita automaticamente."
        ) from error
