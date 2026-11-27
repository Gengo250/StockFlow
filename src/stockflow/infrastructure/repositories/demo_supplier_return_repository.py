"""US30 em memória: histórico e saídas publicados sob o mesmo lock do ledger."""
from datetime import datetime
from uuid import uuid4

from stockflow.application.dto.supplier_return_input import normalize_supplier_return
from stockflow.domain.enums.purchase_status import PurchaseStatus
from stockflow.domain.supplier_return import SupplierReturn, SupplierReturnItem


class DemoSupplierReturnRepository:
    def __init__(self, products, suppliers, movements, purchases, *, company_id, actor_id, actor_name=""):
        self.products, self.suppliers, self.movements, self.purchases = products, suppliers, movements, purchases
        self.company_id, self.actor_id, self.actor_name = company_id, actor_id, actor_name
        self._returns, self._requests = {}, {}

    def create(self, data):
        data = normalize_supplier_return(data)
        # receive() adquire o lock de compras antes do ledger. Obtemos apenas
        # o snapshot imutável aqui, sem inverter essa ordem entre repositórios.
        purchase = next((row for row in self.purchases.list_all()
                         if row.purchase_id == data.purchase_id), None) if data.purchase_id else None
        with self.movements.lock:
            existing = self._requests.get(data.idempotency_key)
            if existing:
                old_data, return_id = existing
                if old_data != data:
                    raise ValueError("Chave de devolução já usada por outra requisição.")
                return self._returns[return_id]
            supplier = self.suppliers.get(data.supplier_id)
            if supplier is None:
                raise LookupError("Fornecedor não encontrado nesta empresa.")
            if data.purchase_id:
                if purchase is None or purchase.status is not PurchaseStatus.RECEBIDA or purchase.supplier_id != data.supplier_id:
                    raise ValueError("Compra de origem deve estar recebida e pertencer ao fornecedor e à empresa.")
                if any(item.product_code not in {row.product_code for row in purchase.items} for item in data.items):
                    raise ValueError("Produto não pertence à compra de origem.")
            return_id = str(uuid4())
            items = tuple(SupplierReturnItem(str(uuid4()), item.product_code,
                self.products[item.product_code].name if item.product_code in self.products else "",
                item.quantity, item.reason, "") for item in data.items)
            now = self.movements._agora or datetime.now().astimezone()
            before_returns, before_requests = dict(self._returns), dict(self._requests)
            def publish(ids):
                result = SupplierReturn(return_id, self.company_id, data.supplier_id, supplier.name,
                    data.purchase_id, self.actor_id, now.isoformat(), data.idempotency_key,
                    tuple(SupplierReturnItem(item.item_id, item.product_code, item.product_name,
                        item.quantity, item.reason, movement_id) for item, movement_id in zip(items, ids)), self.actor_name)
                self._returns[return_id] = result
                self._requests[data.idempotency_key] = (data, return_id)
            try:
                self.movements.register_supplier_return(return_id, data.supplier_id, data.purchase_id, items,
                    created_by=self.actor_id, company_id=self.company_id, created_on=now, publish=publish)
            except BaseException:
                self._returns, self._requests = before_returns, before_requests
                raise
            return self._returns[return_id]

    def get(self, return_id):
        with self.movements.lock:
            if return_id not in self._returns:
                raise LookupError("Devolução não encontrada ou sem permissão.")
            return self._returns[return_id]

    def list_all(self, *, supplier_id=None, purchase_id=None, limit=50, offset=0):
        with self.movements.lock:
            rows = sorted(self._returns.values(), key=lambda row: (row.created_on, row.return_id), reverse=True)
            rows = [row for row in rows if (supplier_id is None or row.supplier_id == supplier_id)
                    and (purchase_id is None or row.purchase_id == purchase_id)]
            return tuple(rows[offset:offset + limit])
