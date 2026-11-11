"""Caixa demonstrativo; vendas compartilham a sessão em memória."""
from decimal import Decimal
from uuid import uuid4

from stockflow.application.services.cash_register_service import closing_summary, payment_totals


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

    def _session(self, register_log_id):
        if register_log_id is not None:
            if self._current and register_log_id == self._current['id']:
                return self._current
            for closed in self.history:
                if closed['id'] == register_log_id:
                    return closed
            raise ValueError('A sessão de caixa mudou. Atualize antes de fechar.')
        if not self._current:
            raise ValueError('Não há caixa aberto.')
        return self._current

    def _summary(self, session):
        rows = [row for row in self.sales.rows if row.get('register_log_id') == session['id']]
        return closing_summary(session['initial_balance'], payment_totals(rows))

    def summary(self, *, register_log_id=None):
        session = self._session(register_log_id)
        if session.get('status') == 'CLOSED':
            return dict(session, register_log_id=session['id'])
        return dict(self._summary(session), register_log_id=session['id'], status='OPEN')

    def close(self, declared, justification, *, register_log_id=None):
        if not self._current:
            raise ValueError('Não há caixa aberto.')
        if register_log_id is not None and register_log_id != self._current['id']:
            raise ValueError('A sessão de caixa mudou. Atualize antes de fechar.')
        summary = self._summary(self._current)
        counted = sum(declared.values(), Decimal(0))
        difference = counted - summary['total_expected']
        if difference and not justification:
            raise ValueError('Divergência de valores. Informe uma justificativa.')
        result = dict(self._current, **summary, status='CLOSED', declared=dict(declared),
                      total_declared=counted, difference=difference, justification=justification)
        self.history.append(result)
        self._current = None
        return result
