"""Movimentações em memória para o catálogo demonstrativo, sem persistência."""
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.movement_status import MovementStatus


class DemoMovements:
    def __init__(self, products):
        self.products = products
        self.rows = []

    def _product(self, code):
        product = self.products.get(code)
        if product is None or not product.active:
            raise ValueError('Selecione um produto ativo.')
        return product

    def _apply(self, code, kind, quantity):
        product = self._product(code)
        before = int(product.stock)
        after = before + kind.sinal * quantity
        if after < 0:
            raise ValueError(f'Estoque insuficiente: {before} unidades disponíveis.')
        # Faixas do catálogo demonstrativo: até 2 crítico, até 6 baixo.
        status = 'Crítico' if after <= 2 else 'Baixo' if after <= 6 else 'Normal'
        self.products[code] = replace(product, stock=str(after), stock_status=status)
        return before, after

    def register(self, data, party_name, allowed):
        if not allowed:
            raise ValueError('Você não tem permissão para movimentar o estoque.')
        product = self._product(data.product_code)
        kind = MovementKind.from_value(data.kind)
        if type(data.quantity) is not int or data.quantity <= 0:
            raise ValueError('Informe uma quantidade inteira maior que zero.')
        if kind == MovementKind.ENTRADA and (not data.supplier_id or not party_name):
            raise ValueError('Selecione um fornecedor ativo para a entrada.')
        before, after = (None, None)
        if data.confirm:
            before, after = self._apply(product.code, kind, data.quantity)
        status = MovementStatus.CONFIRMADA if data.confirm else MovementStatus.PENDENTE
        row = (str(uuid4()), product.code, product.name, kind.label, data.quantity,
               status.label, data.note, datetime.now(timezone.utc).isoformat(),
               party_name, before, after, 'Manual · Demonstração', 'Usuário demonstrativo', None)
        self.rows.append(row)

    def transition(self, movement_id, confirm, allowed):
        if not allowed:
            raise ValueError('Você não tem permissão para movimentar o estoque.')
        index = next((i for i, row in enumerate(self.rows) if row[0] == movement_id), None)
        if index is None or self.rows[index][5] != MovementStatus.PENDENTE.label:
            raise ValueError('Apenas movimentações pendentes podem ser alteradas.')
        row = list(self.rows[index])
        if confirm:
            kind = next(kind for kind in MovementKind if kind.label == row[3])
            row[9], row[10] = self._apply(row[1], kind, row[4])
        row[5] = (MovementStatus.CONFIRMADA if confirm else MovementStatus.CANCELADA).label
        self.rows[index] = tuple(row)
