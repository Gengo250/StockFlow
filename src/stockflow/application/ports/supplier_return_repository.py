from typing import Protocol
from stockflow.application.dto.supplier_return_input import SupplierReturnInput
from stockflow.domain.supplier_return import SupplierReturn


class SupplierReturnRepository(Protocol):
    company_id: str

    def create(self, data: SupplierReturnInput) -> SupplierReturn: ...

    def get(self, return_id: str) -> SupplierReturn: ...

    def list_all(self, *, supplier_id=None, purchase_id=None, limit=50, offset=0) -> tuple[SupplierReturn, ...]: ...
