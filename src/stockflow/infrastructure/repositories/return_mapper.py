"""Mapeamento defensivo das RPCs US20 e de seus argumentos."""

from dataclasses import asdict

from stockflow.application.dto.return_dto import ReturnResultDTO, parse_return_result
from stockflow.application.dto.return_eligibility import parse_returnable_items
from stockflow.domain.sale_return import return_identifier, validate_return_request


def return_items_from_response(value: object) -> list[dict]:
    return [asdict(item) for item in parse_returnable_items(value)]


def return_result_from_response(value: object) -> ReturnResultDTO:
    return parse_return_result(value)


def partial_return_args(sale_id, items, reason, idempotency_key) -> dict:
    idempotency_key = return_identifier(idempotency_key)
    if not isinstance(items, (list, tuple)) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Informe itens de devolução válidos.")
    sale_id, normalized, reason = validate_return_request(
        sale_id, [(item.get("sale_item_id"), item.get("quantity")) for item in items], reason
    )
    return {
        "p_sale_id": sale_id,
        "p_items": [{"sale_item_id": key, "quantity": qty} for key, qty in sorted(normalized)],
        "p_reason": reason,
        "p_idempotency_key": idempotency_key,
    }
