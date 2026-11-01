"""DTOs for devolução de itens (return eligibility)."""

from __future__ import annotations

from dataclasses import dataclass

from stockflow.domain.sale_return import return_identifier, return_quantity


@dataclass(frozen=True)
class ReturnEligibilityDTO:
    """Identifica a venda para a qual queremos saber itens devolvíveis."""

    sale_id: str


@dataclass(frozen=True)
class ReturnableItemDTO:
    """Representa um item de venda que ainda pode ser devolvido."""

    sale_item_id: str
    product_id: str | None
    product_name: str
    quantity_sold: int
    quantity_returned: int
    max_returnable: int


def parse_returnable_items(value: object) -> list[ReturnableItemDTO]:
    try:
        if not isinstance(value, list):
            raise ValueError("A RPC deve retornar uma lista, inclusive quando vazia.")
        result = []
        seen = set()
        for row in value:
            if not isinstance(row, dict) or not isinstance(row.get("product_name"), str):
                raise ValueError("Item devolvível inválido.")
            item_id = return_identifier(row["sale_item_id"])
            product_id = row["product_id"]
            if product_id is not None:
                product_id = return_identifier(product_id)
            sold = return_quantity(row["quantity_sold"])
            returned = return_quantity(row["quantity_returned"], allow_zero=True)
            available = return_quantity(row["max_returnable"])
            if item_id in seen or sold - returned != available:
                raise ValueError("Quantidades devolvíveis inconsistentes.")
            seen.add(item_id)
            result.append(ReturnableItemDTO(
                item_id, product_id, row["product_name"], sold, returned, available
            ))
        return result
    except (KeyError, ValueError, TypeError) as error:
        raise RuntimeError("Resposta de itens devolvíveis inválida.") from error
