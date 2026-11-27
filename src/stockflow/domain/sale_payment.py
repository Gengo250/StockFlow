"""Modelo e validação de pagamentos e troco (US18)."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_PAYMENT = Decimal("100000000")

MVP_PAYMENT_METHODS = ("DINHEIRO", "DEBITO", "CREDITO", "PIX")
PAYMENT_METHODS = ("DINHEIRO", "DEBITO", "CREDITO", "PIX", "VALE", "OUTRO")

PAYMENT_METHOD_LABELS = {
    "DINHEIRO": "Dinheiro",
    "DEBITO": "Cartão de débito",
    "CREDITO": "Cartão de crédito",
    "PIX": "Pix",
    "VALE": "Vale",
    "OUTRO": "Outro",
}


@dataclass(frozen=True)
class SalePaymentInput:
    """Entrada bruta de uma linha de pagamento informada pelo operador."""

    payment_method: str
    received_amount: Decimal | str | int | float


@dataclass(frozen=True)
class SalePayment:
    """Pagamento normalizado com valor aplicado, recebido e troco."""

    payment_method: str
    amount: Decimal
    received_amount: Decimal
    change_amount: Decimal = ZERO

    def to_dict(self) -> dict[str, str]:
        return {
            "payment_method": self.payment_method,
            "amount": str(self.amount),
            "received_amount": str(self.received_amount),
            "change_amount": str(self.change_amount),
        }


@dataclass(frozen=True)
class PaymentBreakdown:
    """Resumo consolidado dos pagamentos de uma venda."""

    payments: tuple[SalePayment, ...]
    total_applied: Decimal
    total_received: Decimal
    total_change: Decimal


def _parse_positive_money(value) -> Decimal:
    if isinstance(value, bool) or value is None or str(value).strip() == "":
        raise ValueError("Informe um valor de pagamento maior que zero.")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Valor de pagamento inválido.") from error
    if not amount.is_finite() or amount <= ZERO or amount >= MAX_PAYMENT:
        raise ValueError("O valor do pagamento deve ser maior que zero.")
    quantized = amount.quantize(CENT)
    if quantized != amount:
        raise ValueError("O valor do pagamento deve ter no máximo duas casas decimais.")
    return quantized


def _extract_entry(entry) -> tuple[str, Decimal]:
    if isinstance(entry, SalePaymentInput):
        raw_method = entry.payment_method
        raw_amount = entry.received_amount
    elif isinstance(entry, SalePayment):
        raw_method = entry.payment_method
        raw_amount = entry.received_amount
    elif isinstance(entry, dict):
        raw_method = entry.get("payment_method") or entry.get("method") or ""
        raw_amount = entry.get("received_amount")
        if raw_amount is None or str(raw_amount).strip() == "":
            raw_amount = entry.get("amount")
    else:
        raise ValueError("Formato de pagamento inválido.")

    method = str(raw_method or "").strip().upper()
    return method, _parse_positive_money(raw_amount)


def validate_and_calculate_payments(
    entries,
    sale_total: Decimal,
    allowed_methods: tuple[str, ...] = PAYMENT_METHODS,
) -> PaymentBreakdown:
    """Valida formas, valores positivos, soma exata e calcula troco em dinheiro."""
    total = Decimal(str(sale_total)).quantize(CENT)
    if total < ZERO:
        raise ValueError("Total da venda inválido.")

    raw_entries = list(entries or ())
    if total == ZERO:
        if raw_entries:
            raise ValueError("Venda com total zerado não aceita pagamentos positivos.")
        return PaymentBreakdown(
            payments=(),
            total_applied=ZERO,
            total_received=ZERO,
            total_change=ZERO,
        )

    if not raw_entries:
        raise ValueError("Informe pelo menos uma forma de pagamento.")

    parsed: list[tuple[str, Decimal]] = []
    for entry in raw_entries:
        method, received = _extract_entry(entry)
        if method not in allowed_methods:
            raise ValueError("Selecione uma forma de pagamento válida.")
        parsed.append((method, received))

    non_cash_sum = sum(
        (received for method, received in parsed if method != "DINHEIRO"),
        start=ZERO,
    )
    if non_cash_sum > total:
        raise ValueError(
            "A soma dos pagamentos fora do dinheiro não pode exceder o total da venda."
        )

    remaining_for_cash = total - non_cash_sum
    has_cash = any(method == "DINHEIRO" for method, _ in parsed)
    if has_cash and remaining_for_cash <= ZERO:
        raise ValueError(
            "O total da venda já foi coberto pelas demais formas de pagamento."
        )

    cash_received_sum = sum(
        (received for method, received in parsed if method == "DINHEIRO"),
        start=ZERO,
    )
    total_received = non_cash_sum + cash_received_sum
    if non_cash_sum + cash_received_sum < total:
        raise ValueError(
            "A soma dos pagamentos deve ser igual ao total da venda."
        )
    if not has_cash and non_cash_sum != total:
        raise ValueError(
            "A soma dos pagamentos deve ser igual ao total da venda."
        )

    cash_remaining = remaining_for_cash
    normalized: list[SalePayment] = []
    for method, received in parsed:
        if method != "DINHEIRO":
            normalized.append(
                SalePayment(
                    payment_method=method,
                    amount=received,
                    received_amount=received,
                    change_amount=ZERO,
                )
            )
            continue
        if cash_remaining <= ZERO:
            raise ValueError(
                "Pagamento em dinheiro excedente: cada linha deve abater parte do total."
            )
        applied = min(received, cash_remaining)
        change = (received - applied).quantize(CENT)
        cash_remaining -= applied
        normalized.append(
            SalePayment(
                payment_method="DINHEIRO",
                amount=applied,
                received_amount=received,
                change_amount=change,
            )
        )

    total_applied = sum((p.amount for p in normalized), start=ZERO).quantize(CENT)
    total_change = sum((p.change_amount for p in normalized), start=ZERO).quantize(CENT)
    if total_applied != total:
        raise ValueError("A soma dos pagamentos deve ser igual ao total da venda.")

    return PaymentBreakdown(
        payments=tuple(normalized),
        total_applied=total_applied,
        total_received=total_received.quantize(CENT),
        total_change=total_change,
    )
