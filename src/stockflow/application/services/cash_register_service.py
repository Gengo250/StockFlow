"""Operações de caixa da sessão autenticada do aplicativo."""
from decimal import Decimal, InvalidOperation

from stockflow.domain.permissions import ensure_can_register_sales

PAYMENT_LABELS = {
    'dinheiro': 'Dinheiro (inclua o saldo inicial)',
    'debito': 'Débito', 'credito': 'Crédito', 'pix': 'Pix',
    'vale': 'Vale', 'outro': 'Outros',
}


def money(value):
    try:
        result = Decimal(str(value))
        if (not result.is_finite() or result < 0 or result > Decimal('99999999.99')
                or result != result.quantize(Decimal('.01'))):
            raise ValueError
        return result
    except (InvalidOperation, ValueError):
        raise ValueError('Informe um valor válido, não negativo, com até duas casas decimais.') from None


class CashRegisterService:
    def __init__(self, repository, session):
        self.repository = repository
        self.session = session

    def current(self):
        ensure_can_register_sales(self.session)
        return self.repository.current()

    def open(self, initial_balance):
        ensure_can_register_sales(self.session)
        return self.repository.open(money(initial_balance))

    def close(self, declared, justification, *, register_log_id=None):
        ensure_can_register_sales(self.session)
        values = {key: money(declared.get(key, 0)) for key in PAYMENT_LABELS}
        return self.repository.close(values, justification.strip() or None, register_log_id=register_log_id)
