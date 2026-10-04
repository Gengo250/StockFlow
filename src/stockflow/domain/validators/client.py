"""Validação de dados opcionais informados para clientes."""

from stockflow.application.dto.client_input import ClientInput


def validate_client(data: ClientInput) -> None:
    """Valida o cliente antes de persistir."""
    name = (data.name or "").strip()
    if not name:
        raise ValueError("Nome do cliente é obrigatório.")

    email = (data.email or "").strip()
    if email and "@" not in email:
        raise ValueError("E-mail do cliente é inválido.")

    phone = _digits(data.phone or "")
    if data.phone and len(phone) not in (10, 11):
        raise ValueError("Telefone do cliente é inválido.")

    document = _digits(data.document or "")
    if data.document and len(document) not in (11, 14):
        raise ValueError("CPF/CNPJ do cliente é inválido.")


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isdigit())
