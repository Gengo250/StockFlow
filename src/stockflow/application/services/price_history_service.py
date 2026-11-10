"""Caso de uso de leitura do histórico de preço e custo (H09) e auditoria (US25)."""

from stockflow.application.dto.audit_filter import (
    AuditFilter,
    AuditPage,
    TAMANHO_MAXIMO_AUDITORIA,
    TAMANHO_PADRAO_AUDITORIA,
)
from stockflow.application.ports.price_history_repository import PriceHistoryRepository
from stockflow.domain.permissions import ensure_can_view_price_history
from stockflow.domain.price_change import PriceChange


class PriceHistoryService:
    def __init__(self, repository: PriceHistoryRepository):
        self._repository = repository

    @property
    def repository(self) -> PriceHistoryRepository:
        return self._repository

    def list_changes(self, session, product_code: str | None = None) -> tuple[PriceChange, ...]:
        """Histórico da empresa, do mais recente para o mais antigo.

        A permissão é verificada antes de QUALQUER chamada ao repositório,
        como em `ProductService.create_product`: quem não pode ler a
        auditoria também não pode gastar a consulta que a leria — e a
        função SQL responderia `insufficient_privilege` de qualquer modo.
        """
        ensure_can_view_price_history(session)
        return self._repository.list_price_edits(product_code)

    def list_audit_page(
        self,
        session,
        filtro: AuditFilter | None = None,
        page: int = 1,
        size: int = TAMANHO_PADRAO_AUDITORIA,
    ) -> AuditPage:
        """Página da consulta de auditoria (US25).

        Apenas perfis autorizados (ADMIN) podem acessar a auditoria.
        Acesso sem permissão dispara PermissionDeniedError.
        """
        ensure_can_view_price_history(session)
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError("Página inválida.")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or not 1 <= size <= TAMANHO_MAXIMO_AUDITORIA
        ):
            raise ValueError(
                f"Tamanho de página inválido: use entre 1 e {TAMANHO_MAXIMO_AUDITORIA}."
            )
        return self._repository.list_audit_page(filtro or AuditFilter(), page, size)

    def list_page(
        self,
        session,
        filtro: AuditFilter | None = None,
        page: int = 1,
        size: int = TAMANHO_PADRAO_AUDITORIA,
    ) -> AuditPage:
        """Alias para list_audit_page, alinhando com SaleService."""
        return self.list_audit_page(session, filtro=filtro, page=page, size=size)
