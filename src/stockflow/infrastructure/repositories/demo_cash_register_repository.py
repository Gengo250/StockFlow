"""Caixa demonstrativo; vendas compartilham a sessão em memória."""
from decimal import Decimal
from uuid import uuid4


class DemoCashRegisterRepository:
    def __init__(self, sales):
        self.sales = sales
        self._current = None
        self.history = []

    def current(self):
        return dict(self._current) if self._current else None

    def open(self, balance):
        if self._current:
            raise ValueError('Você já possui um caixa aberto.')
        self._current = dict(id=str(uuid4()), initial_balance=balance, status='OPEN')
        return self.current()

    def close(self, declared, justification, *, register_log_id=None):
        if not self._current:
            raise ValueError('Não há caixa aberto.')
        if register_log_id is not None and register_log_id != self._current['id']:
            raise ValueError('A sessão de caixa mudou. Atualize antes de fechar.')
        total = sum((Decimal(str(row['total'])) for row in self.sales.rows
                     if row.get('register_log_id') == self._current['id']
                     and row.get('status') == 'CONCLUIDA'), Decimal(0))
        expected = self._current['initial_balance'] + total
        counted = sum(declared.values(), Decimal(0))
        difference = counted - expected
        if difference and not justification:
            raise ValueError('Divergência de valores. Informe uma justificativa.')
        result = dict(self._current, status='CLOSED', total_sales=total,
                      total_expected=expected, total_declared=counted,
                      difference=difference, justification=justification)
        self.history.append(result)
        self._current = None
        return result
