"""Operações de caixa da sessão autenticada do aplicativo."""
from decimal import Decimal, InvalidOperation

from stockflow.domain.permissions import ensure_can_register_sales

# Chaves idênticas ao enum public.payment_method do banco.
PAYMENT_LABELS = {
    'DINHEIRO': 'Dinheiro (inclua o saldo inicial)',
    'DEBITO': 'Débito', 'CREDITO': 'Crédito', 'PIX': 'Pix',
    'VALE': 'Vale', 'OUTRO': 'Outros',
}
PAYMENT_METHODS = tuple(PAYMENT_LABELS)
ZERO = Decimal('0.00')
CENT = Decimal('0.01')


def money(value):
    try:
        result = Decimal(str(value))
        if (not result.is_finite() or result < 0 or result > Decimal('99999999.99')
                or result != result.quantize(Decimal('.01'))):
            raise ValueError
        return result
    except (InvalidOperation, ValueError):
        raise ValueError('Informe um valor válido, não negativo, com até duas casas decimais.') from None


def _amount(value):
    return Decimal(str(value if value is not None else 0)).quantize(CENT)


def payment_totals(sales):
    """Soma as vendas CONCLUIDAS por forma de pagamento (espelha fn_register_payment_totals)."""
    totals = dict.fromkeys(PAYMENT_METHODS, ZERO)
    for sale in sales:
        if sale.get('status') != 'CONCLUIDA':
            continue
        method = str(sale.get('payment_method') or 'OUTRO').upper()
        totals[method if method in totals else 'OUTRO'] += _amount(sale.get('total'))
    return totals


def closing_summary(initial_balance, totals):
    """Subtotais por forma de pagamento, total dos totais e valores esperados."""
    initial = _amount(initial_balance)
    totals = {key: _amount(totals.get(key)) for key in PAYMENT_METHODS}
    total_sales = sum(totals.values(), ZERO)  # total dos totais
    return {
        'initial_balance': initial,
        'totals': totals,
        'total_sales': total_sales,
        # O troco inicial fica na gaveta junto com o dinheiro das vendas.
        'expected_dinheiro': initial + totals['DINHEIRO'],
        'total_expected': initial + total_sales,
    }


def normalize_summary(data):
    """Converte os números da resposta JSON das RPCs de caixa em Decimal."""
    if not data:
        return data
    result = dict(data)
    for key in ('initial_balance', 'total_sales', 'expected_dinheiro',
                'total_expected', 'total_declared', 'difference'):
        if result.get(key) is not None:
            result[key] = _amount(result[key])
    for group in ('totals', 'declared'):
        if isinstance(result.get(group), dict):
            values = {str(k).upper(): v for k, v in result[group].items()}
            result[group] = {key: _amount(values.get(key)) for key in PAYMENT_METHODS}
    return result


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

    def summary(self, *, register_log_id=None):
        """Prévia automática do fechamento: totais por forma e total geral."""
        ensure_can_register_sales(self.session)
        return normalize_summary(self.repository.summary(register_log_id=register_log_id))

    def close(self, declared, justification, *, register_log_id=None):
        ensure_can_register_sales(self.session)
        declared = {str(key).upper(): value for key, value in declared.items()}
        values = {key: money(declared.get(key, 0)) for key in PAYMENT_METHODS}
        result = self.repository.close(values, justification.strip() or None, register_log_id=register_log_id)
        return normalize_summary(result)
