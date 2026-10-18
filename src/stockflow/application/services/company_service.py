"""Casos de uso de administração da empresa (H31 - Teto de Estoque)."""

from stockflow.application.ports.company_repository import CompanyRepository
from stockflow.domain.permissions import ensure_can_manage_companies


class CompanyService:
    """Serviço de aplicação para governança e configurações da empresa."""

    def __init__(self, repository: CompanyRepository):
        self._repo = repository

    def set_max_stock_limit(
        self, session, new_limit: int, company_id: str | None = None
    ) -> int:
        """Altera o teto global de estoque da empresa (H31).

        Apenas ADMIN pode chamar. O limite não pode ser negativo nem inferior
        ao estoque máximo já configurado para qualquer produto da empresa.

        Args:
            session: Sessão do usuário logado (exige role ADMIN).
            new_limit: Novo teto operacional (inteiro >= 0).
            company_id: Opcional. Se omitido, usa o da própria sessão.

        Returns:
            O limite efetivamente gravado.

        Raises:
            PermissionDeniedError: Se o usuário não for ADMIN.
            ValueError: Se o valor for negativo ou inválido.
        """
        # Segurança: Apenas administradores podem gerenciar configurações da empresa
        ensure_can_manage_companies(session, action="alterar teto de estoque da empresa")

        #Resolução da empresa alvo
        target_company = company_id or getattr(session, "company_id", None)
        if not target_company:
            raise ValueError("Identificador da empresa não informado ou ausente na sessão.")

        if new_limit is None or not isinstance(new_limit, int) or new_limit < 0:
            raise ValueError(
                f"O teto de estoque deve ser um número inteiro maior ou igual a zero (recebido: {new_limit})."
            )

        # 4. Delegação à persistência (RPC fn_set_company_max_stock_limit)
        self._repo.set_company_max_stock_limit(str(target_company), new_limit)
        return new_limit

    def get_max_stock_limit(self, session, company_id: str | None = None) -> int:
        """Consulta o teto global de estoque atual da empresa.
        """
        target_company = company_id or getattr(session, "company_id", None)
        if not target_company:
            raise ValueError("Identificador da empresa não informado ou ausente na sessão.")

        return self._repo.get_company_max_stock_limit(str(target_company))