from dataclasses import dataclass


@dataclass(frozen=True)
class SupplierInput:
    """Dados do formulário de fornecedores."""

    supplier_id: str | None = None
    name: str = ""
    document: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    active: bool | None = None
