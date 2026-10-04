"""Normalização e validação de CPF/CNPJ brasileiros."""


def normalize_br_document(value: str | None) -> str:
    """Retorna o documento sem formatação, vazio quando não informado."""
    return "".join(ch for ch in (value or "") if "0" <= ch <= "9")


def is_valid_br_document(document: str) -> bool:
    """Valida CPF/CNPJ pelos dígitos verificadores."""
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
