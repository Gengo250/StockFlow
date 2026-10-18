
from typing import Protocol


class CompanyRepository(Protocol):
    """Contrato de acesso e governança da empresa."""

    def set_company_max_stock_limit(self, company_id: str, limit: int) -> None:
        """Grava o novo teto de estoque da empresa via RPC autorizada."""
        ...

    def get_company_max_stock_limit(self, company_id: str) -> int:
        """Lê o teto configurado para a empresa."""
        ...