from dataclasses import dataclass


@dataclass(frozen=True)
class ClientInput:
    """Dados de entrada do formulário de clientes."""

    client_id: str | None = None
    name: str = ""
    email: str = ""
    phone: str = ""
    document: str = ""
    active: bool | None = None
    notes: str = ""
