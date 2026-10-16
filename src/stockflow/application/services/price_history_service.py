"""Caso de uso de leitura do histórico de preço e custo (H09)."""

from stockflow.application.ports.price_history_repository import PriceHistoryRepository
from stockflow.domain.permissions import ensure_can_view_price_history
from stockflow.domain.price_change import PriceChange


class PriceHistoryService:
    def __init__(self, repository: PriceHistoryRepository):
        self._repository = repository

    def list_changes(self, session, product_code: str | None = None) -> tuple[PriceChange, ...]:
        """Histórico da empresa, do mais recente para o mais antigo.

        A permissão é verificada antes de QUALQUER chamada ao repositório,
        como em `ProductService.create_product`: quem não pode ler a
        auditoria também não pode gastar a consulta que a leria — e a
        função SQL responderia `insufficient_privilege` de qualquer modo.
        """
        ensure_can_view_price_history(session)
        return self._repository.list_price_edits(product_code)
