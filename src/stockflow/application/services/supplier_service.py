"""Casos de uso de gestão de fornecedores."""

from stockflow.application.dto.supplier_input import SupplierInput
from stockflow.application.ports.supplier_repository import SupplierRepository
from stockflow.domain.entities.supplier import Supplier
from stockflow.domain.permissions import ensure_can_manage_suppliers
from stockflow.domain.validators.supplier import normalize_document, validate_supplier


class SupplierService:
    def __init__(self, repository: SupplierRepository):
        self._repository = repository

    def list_suppliers(self, session) -> tuple[Supplier, ...]:
        ensure_can_manage_suppliers(session, action="consultar fornecedores")
        return self._repository.list_all()

    def search_suppliers(self, session, query: str = "") -> tuple[Supplier, ...]:
        ensure_can_manage_suppliers(session, action="consultar fornecedores")
        return self._repository.search(query)

    def get_supplier(self, session, supplier_id: str) -> Supplier | None:
        ensure_can_manage_suppliers(session, action="consultar fornecedores")
        return self._repository.get(supplier_id)

    def create_supplier(self, session, data: SupplierInput) -> Supplier:
        ensure_can_manage_suppliers(session, action="cadastrar fornecedores")
        validate_supplier(data)
        if self._duplicate_document(data.document) is not None:
            raise ValueError("Já existe um fornecedor com este CPF/CNPJ.")
        supplier_id = data.supplier_id or self._repository.next_id()
        return self._repository.create(
            SupplierInput(
                supplier_id=supplier_id,
                name=data.name.strip(),
                document=normalize_document(data.document),
                phone=(data.phone or "").strip(),
                email=(data.email or "").strip(),
                address=(data.address or "").strip(),
                active=bool(data.active if data.active is not None else True),
            )
        )

    def update_supplier(self, session, supplier_id: str, data: SupplierInput) -> Supplier:
        ensure_can_manage_suppliers(session, action="editar fornecedores")
        current = self._repository.get(supplier_id)
        if current is None:
            raise LookupError(f"Fornecedor {supplier_id} não encontrado.")
        validate_supplier(data)
        duplicate = self._duplicate_document(data.document)
        if duplicate is not None and duplicate.supplier_id != supplier_id:
            raise ValueError("Já existe um fornecedor com este CPF/CNPJ.")
        return self._repository.update(
            supplier_id,
            SupplierInput(
                supplier_id=supplier_id,
                name=(data.name if data.name is not None else current.name).strip(),
                document=normalize_document(
                    data.document if data.document is not None else current.document
                ),
                phone=(data.phone if data.phone is not None else current.phone).strip(),
                email=(data.email if data.email is not None else current.email).strip(),
                address=(data.address if data.address is not None else current.address).strip(),
                active=data.active if data.active is not None else current.active,
            ),
        )

    def set_active(self, session, supplier_id: str, active: bool) -> Supplier:
        ensure_can_manage_suppliers(session, action="alterar status de fornecedores")
        if not self._repository.exists(supplier_id):
            raise LookupError(f"Fornecedor {supplier_id} não encontrado.")
        self._repository.set_active(supplier_id, bool(active))
        updated = self._repository.get(supplier_id)
        if updated is None:
            raise LookupError(f"Fornecedor {supplier_id} não encontrado.")
        return updated

    def _duplicate_document(self, document: str | None) -> Supplier | None:
        normalized = normalize_document(document)
        return self._repository.find_by_document(normalized) if normalized else None
