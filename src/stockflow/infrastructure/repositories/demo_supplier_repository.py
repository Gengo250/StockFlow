"""Persistência demonstrativa de fornecedores em memória."""

from stockflow.application.dto.supplier_input import SupplierInput
from stockflow.domain.entities.supplier import Supplier
from stockflow.domain.validators.supplier import normalize_document


class DemoSupplierRepository:
    """Repositório compartilhável entre as telas de fornecedor e seleção."""

    def __init__(self, suppliers=None):
        self._suppliers = suppliers if suppliers is not None else {
            "FOR-001": Supplier(
                "FOR-001", "Distribuidora Central", "", "(11) 3333-4444",
                "contato@central.example", "São Paulo - SP", True,
            ),
            "FOR-002": Supplier(
                "FOR-002", "Fornecedor Inativo", "", "", "", "", False,
            ),
        }

    def list_all(self):
        return tuple(self._suppliers.values())

    def list_active(self):
        return tuple(s for s in self._suppliers.values() if s.active)

    def search(self, query: str):
        term = (query or "").strip().casefold()
        digits = normalize_document(term)
        if not term:
            return self.list_all()
        return tuple(
            supplier for supplier in self._suppliers.values()
            if term in supplier.name.casefold()
            or term in supplier.email.casefold()
            or term in supplier.phone.casefold()
            or term in supplier.address.casefold()
            or (digits and digits in normalize_document(supplier.document))
            or (digits and digits in normalize_document(supplier.phone))
        )

    def find_by_document(self, document: str):
        normalized = normalize_document(document)
        if not normalized:
            return None
        return next(
            (s for s in self._suppliers.values()
             if normalize_document(s.document) == normalized),
            None,
        )

    def get(self, supplier_id: str):
        return self._suppliers.get(supplier_id)

    def exists(self, supplier_id: str) -> bool:
        return supplier_id in self._suppliers

    def next_id(self) -> str:
        prefix = "FOR-"
        numbers = [
            int(key[len(prefix):])
            for key in self._suppliers
            if key.startswith(prefix) and key[len(prefix):].isdigit()
        ]
        return f"{prefix}{max(numbers, default=0) + 1:03d}"

    def create(self, data: SupplierInput):
        if data.supplier_id in self._suppliers:
            raise ValueError(f"Já existe um fornecedor com o código {data.supplier_id}.")
        supplier = Supplier(
            supplier_id=data.supplier_id or self.next_id(),
            name=data.name,
            document=normalize_document(data.document),
            phone=data.phone,
            email=data.email,
            address=data.address,
            active=bool(data.active),
        )
        self._suppliers[supplier.supplier_id] = supplier
        return supplier

    def update(self, supplier_id: str, data: SupplierInput):
        if supplier_id not in self._suppliers:
            raise LookupError(f"Fornecedor {supplier_id} não encontrado.")
        supplier = Supplier(
            supplier_id=supplier_id,
            name=data.name,
            document=normalize_document(data.document),
            phone=data.phone,
            email=data.email,
            address=data.address,
            active=bool(data.active),
        )
        self._suppliers[supplier_id] = supplier
        return supplier

    def set_active(self, supplier_id: str, active: bool) -> None:
        supplier = self.get(supplier_id)
        if supplier is None:
            raise LookupError(f"Fornecedor {supplier_id} não encontrado.")
        supplier.active = bool(active)
