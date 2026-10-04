from dataclasses import dataclass


@dataclass
class Supplier:
    """Fornecedor da empresa, mantido sem exclusão física."""

    supplier_id: str
    name: str
    document: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    active: bool = True

    @property
    def status(self) -> str:
        return "Ativo" if self.active else "Inativo"

    @property
    def is_active(self) -> bool:
        return self.active
