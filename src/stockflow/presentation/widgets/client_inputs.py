"""Formatted inputs for Brazilian client documents and phone numbers."""

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QLineEdit

from stockflow.domain.validators.client import normalize_document


class _DigitsValidator(QValidator):
    def __init__(self, maximum_digits: int, allowed: str, parent=None):
        super().__init__(parent)
        self._maximum_digits = maximum_digits
        self._allowed = set(allowed)

    def validate(self, text: str, position: int):
        digits = normalize_document(text)
        valid_characters = all(char in self._allowed for char in text)
        if len(digits) > self._maximum_digits or not valid_characters:
            return QValidator.Invalid, text, position
        return QValidator.Acceptable, text, position


class _FormattedLineEdit(QLineEdit):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.textEdited.connect(self._format_edited_text)
        if text:
            self.setText(self.format_value(text))

    def format_value(self, value: str) -> str:
        raise NotImplementedError

    def _format_edited_text(self, text: str):
        cursor = self.cursorPosition()
        digits_before_cursor = len(normalize_document(text[:cursor]))
        formatted = self.format_value(text)
        if formatted == text:
            return

        self.setText(formatted)
        if digits_before_cursor == 0:
            self.setCursorPosition(0)
            return

        seen = 0
        for index, char in enumerate(formatted):
            if char.isdigit():
                seen += 1
                if seen == digits_before_cursor:
                    self.setCursorPosition(index + 1)
                    return
        self.setCursorPosition(len(formatted))


class ClientDocumentInput(_FormattedLineEdit):
    """Formats 11 digits as CPF or 14 digits as CNPJ while typing."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("clientDocumentInput")
        self.setPlaceholderText("CPF ou CNPJ")
        self.setAccessibleName("CPF ou CNPJ")
        self.setValidator(_DigitsValidator(14, "0123456789./ -", self))

    def format_value(self, value: str) -> str:
        digits = normalize_document(value)[:14]
        if len(digits) > 11:
            parts = (
                digits[:2],
                digits[2:5],
                digits[5:8],
                digits[8:12],
                digits[12:14],
            )
            result = parts[0]
            if len(digits) > 2:
                result += "." + parts[1]
            if len(digits) > 5:
                result += "." + parts[2]
            if len(digits) > 8:
                result += "/" + parts[3]
            if len(digits) > 12:
                result += "-" + parts[4]
            return result

        result = digits[:3]
        if len(digits) > 3:
            result += "." + digits[3:6]
        if len(digits) > 6:
            result += "." + digits[6:9]
        if len(digits) > 9:
            result += "-" + digits[9:11]
        return result


class ClientPhoneInput(_FormattedLineEdit):
    """Formats Brazilian 10-digit landlines and 11-digit mobile numbers."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("clientPhoneInput")
        self.setPlaceholderText("(00) 0000-0000")
        self.setAccessibleName("Telefone com DDD")
        self.setValidator(_DigitsValidator(11, "0123456789().- ", self))

    def format_value(self, value: str) -> str:
        digits = normalize_document(value)[:11]
        if len(digits) <= 2:
            return f"({digits}" if digits else ""

        result = f"({digits[:2]}) "
        local = digits[2:]
        if len(digits) > 10:
            result += local[:5]
            if len(local) > 5:
                result += "-" + local[5:10]
        else:
            result += local[:4]
            if len(local) > 4:
                result += "-" + local[4:9]
        return result
