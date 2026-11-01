"""Casos de uso US20: autorização, validação e coordenação da porta de vendas."""

from stockflow.application.dto.return_dto import (
    CreateReturnDTO, ReturnItemDTO, ReturnResultDTO, parse_return_result,
)
from stockflow.application.dto.return_eligibility import (
    ReturnEligibilityDTO, ReturnableItemDTO, parse_returnable_items,
)
from stockflow.application.ports.sale_repository import SaleRepository
from stockflow.domain.permissions import ensure_can_return_sales
from stockflow.domain.sale_return import return_identifier, validate_return_request


class ReturnEligibilityService:
    def __init__(self, sale_repository: SaleRepository, session=None):
        self._sale_repository = sale_repository
        self._session = session

    def get_returnable(self, dto: ReturnEligibilityDTO) -> list[ReturnableItemDTO]:
        ensure_can_return_sales(self._session, "consultar itens devolvíveis")
        sale_id = return_identifier(dto.sale_id)
        return parse_returnable_items(self._sale_repository.get_returnable_items(sale_id))


class ReturnService:
    def __init__(self, sale_repository: SaleRepository, session=None):
        self._sale_repository = sale_repository
        self._session = session

    def create_return(self, dto: CreateReturnDTO) -> ReturnResultDTO:
        ensure_can_return_sales(self._session)
        idempotency_key = return_identifier(dto.idempotency_key)
        if not isinstance(dto.items, (list, tuple)) or any(
            not isinstance(item, ReturnItemDTO) for item in dto.items
        ):
            raise ValueError("Informe itens de devolução válidos.")
        sale_id, items, reason = validate_return_request(
            dto.sale_id, [(item.sale_item_id, item.quantity) for item in dto.items], dto.reason
        )
        payload = [{"sale_item_id": key, "quantity": qty} for key, qty in items]
        # Só uma escrita, sem retries, compensação de estoque ou chamada fiscal.
        return parse_return_result(self._sale_repository.partial_return(
            sale_id, payload, reason, idempotency_key
        ))
