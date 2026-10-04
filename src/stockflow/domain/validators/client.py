"""Validação de dados opcionais informados para clientes."""

import re

from stockflow.application.dto.client_input import ClientInput

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^[+0-9().\s-]+$")
DOCUMENT_PATTERN = re.compile(r"^[0-9./\s-]+$")


def validate_client(data: ClientInput) -> None:
    """Valida o cliente antes de persistir."""
    name = (data.name or "").strip()
    if not name:
        raise ValueError("Nome do cliente é obrigatório.")

    email = (data.email or "").strip()
    if email and not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("E-mail do cliente é inválido.")

    raw_phone = (data.phone or "").strip()
    phone = normalize_document(data.phone)
    if raw_phone and (
        not PHONE_PATTERN.fullmatch(raw_phone) or len(phone) not in (10, 11)
    ):
        raise ValueError("Telefone do cliente é inválido.")

    raw_document = (data.document or "").strip()
    document = normalize_document(data.document)
    if raw_document and (
        not DOCUMENT_PATTERN.fullmatch(raw_document)
        or not _valid_brazilian_document(document)
    ):
        raise ValueError("CPF/CNPJ do cliente é inválido.")


def normalize_document(value: str | None) -> str:
    """Retorna o documento sem formatação, vazio quando não informado."""
    return "".join(ch for ch in (value or "") if "0" <= ch <= "9")


def _valid_brazilian_document(document: str) -> bool:
    if len(document) == 11 and len(set(document)) != 1:
        digits = [int(char) for char in document]
        first = sum(value * weight for value, weight in zip(digits[:9], range(10, 1, -1)))
        first_digit = 0 if first % 11 < 2 else 11 - first % 11
        second = sum(value * weight for value, weight in zip(digits[:9], range(11, 2, -1)))
        second += first_digit * 2
        second_digit = 0 if second % 11 < 2 else 11 - second % 11
        return digits[9:] == [first_digit, second_digit]

    if len(document) == 14 and len(set(document)) != 1:
        digits = [int(char) for char in document]
        first_weights = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
        first = sum(value * weight for value, weight in zip(digits[:12], first_weights))
        first_digit = 0 if first % 11 < 2 else 11 - first % 11
        second_weights = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
        second = sum(value * weight for value, weight in zip(digits[:12], second_weights))
        second += first_digit * second_weights[-1]
        second_digit = 0 if second % 11 < 2 else 11 - second % 11
        return digits[12:] == [first_digit, second_digit]

    return False
