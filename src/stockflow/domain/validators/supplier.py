"""Validação dos dados de fornecedores."""

import re

from stockflow.application.dto.supplier_input import SupplierInput
from stockflow.domain.validators.br_document import (
    is_valid_br_document,
    normalize_br_document,
)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^[+0-9().\s-]+$")
DOCUMENT_PATTERN = re.compile(r"^[0-9./\s-]+$")


def validate_supplier(data: SupplierInput) -> None:
    if not (data.name or "").strip():
        raise ValueError("Nome ou razão social do fornecedor é obrigatório.")

    email = (data.email or "").strip()
    if email and not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("E-mail do fornecedor é inválido.")

    raw_phone = (data.phone or "").strip()
    phone_digits = normalize_br_document(raw_phone)
    if raw_phone and (
        not PHONE_PATTERN.fullmatch(raw_phone) or len(phone_digits) not in (10, 11)
    ):
        raise ValueError("Telefone do fornecedor é inválido.")

    raw_document = (data.document or "").strip()
    document = normalize_br_document(raw_document)
    if raw_document and (
        not DOCUMENT_PATTERN.fullmatch(raw_document)
        or not is_valid_br_document(document)
    ):
        raise ValueError("CPF/CNPJ do fornecedor é inválido.")


def normalize_document(value: str | None) -> str:
    return normalize_br_document(value)
