from dataclasses import dataclass


@dataclass
class Client:
    """Cliente da empresa, mantenido por nome e status lógico."""

    client_id: str
    name: str
    email: str = ""
    phone: str = ""
    document: str = ""
    active: bool = True
    notes: str = ""

    @property
    def status(self) -> str:
        return "Ativo" if self.active else "Inativo"

    @status.setter
    def status(self, value: str) -> None:
        self.active = str(value).strip().casefold() != "inativo"

    @property
    def is_active(self) -> bool:
        return self.active
