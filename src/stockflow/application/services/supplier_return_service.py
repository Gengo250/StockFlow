"""US30: validação estrutural e uma única escrita transacional no repositório."""
from stockflow.application.dto.supplier_return_input import SupplierReturnInput, normalize_supplier_return
from stockflow.application.ports.supplier_return_repository import SupplierReturnRepository
from stockflow.domain.supplier_return import SupplierReturn
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.permissions import ensure_can_return_to_supplier


class SupplierReturnService:
    def __init__(self, repository: SupplierReturnRepository, session=None):
        self.repository = repository
        self.session = session

    def _authorize(self, action: str) -> None:
        ensure_can_return_to_supplier(self.session, action)
        if str(self.repository.company_id) != str(self.session.company_id):
            raise PermissionDeniedError("operar devoluções de outra empresa", self.session.role)
        actor = getattr(self.repository, "actor_id", self.session.user_id)
        if actor != self.session.user_id:
            raise PermissionDeniedError("operar devoluções de outra sessão", self.session.role)

    def create_return(self, data: SupplierReturnInput) -> SupplierReturn:
        self._authorize("registrar devoluções ao fornecedor")
        # Saldo, vínculos e estado da compra são conferidos novamente sob lock no banco.
        return self.repository.create(normalize_supplier_return(data))

    def get_return(self, return_id: str) -> SupplierReturn:
        self._authorize("consultar devoluções ao fornecedor")
        if not isinstance(return_id, str) or not return_id.strip():
            raise ValueError("Selecione uma devolução ao fornecedor.")
        return self.repository.get(return_id.strip())

    def list_returns(self, *, supplier_id: str | None = None, purchase_id: str | None = None,
                     limit: int = 50, offset: int = 0) -> tuple[SupplierReturn, ...]:
        self._authorize("consultar devoluções ao fornecedor")
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
            raise ValueError("Paginação inválida.")
        for value in (supplier_id, purchase_id):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("Filtro de devolução inválido.")
        return self.repository.list_all(
            supplier_id=supplier_id.strip() if supplier_id else None,
            purchase_id=purchase_id.strip() if purchase_id else None, limit=limit, offset=offset)
