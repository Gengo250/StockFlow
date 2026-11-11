from dataclasses import replace
from datetime import datetime
from threading import RLock

from stockflow.application.dto.purchase_input import PurchaseInput
from stockflow.domain.enums.purchase_status import PurchaseStatus
from stockflow.domain.purchase import Purchase, PurchaseItem


class DemoPurchaseRepository:
    def __init__(self, products, suppliers, movement_repository):
        self._products = products
        self._suppliers = suppliers
        self._movements = movement_repository
        self._purchases = {}
        self._lock = RLock()

    def list_all(self) -> tuple[Purchase, ...]:
        with self._lock:
            return tuple(reversed(tuple(self._purchases.values())))

    def create(self, data: PurchaseInput) -> str:
        with self._lock:
            supplier = self._suppliers.get(data.supplier_id)
            if supplier is None or not supplier.active:
                raise ValueError("Selecione um fornecedor ativo.")
            if not data.items:
                raise ValueError("A compra deve ter pelo menos um item.")

            items = []
            for item in data.items:
                product = self._products.get(item.product_code)
                if product is None or not product.active:
                    raise ValueError("Selecione um produto ativo.")
                items.append(PurchaseItem(product.code, product.name, item.quantity))

            purchase_id = f"PUR-{len(self._purchases) + 1:04d}"
            self._purchases[purchase_id] = Purchase(
                purchase_id, supplier.supplier_id, supplier.name,
                PurchaseStatus.RASCUNHO, tuple(items),
                created_on=datetime.now().isoformat(timespec="seconds"),
            )
            return purchase_id

    def receive(self, purchase_id: str) -> None:
        with self._lock:
            purchase = self._purchases.get(purchase_id)
            if purchase is None:
                raise LookupError(f"Compra {purchase_id} não encontrada.")
            if purchase.status is not PurchaseStatus.RASCUNHO:
                raise ValueError("Só compras em rascunho podem ser recebidas.")

            supplier = self._suppliers.get(purchase.supplier_id)
            if supplier is None or not supplier.active:
                raise ValueError("O fornecedor da compra não está ativo.")
            self._movements.register_purchase(
                purchase.purchase_id, purchase.supplier_id, purchase.items
            )
            self._purchases[purchase_id] = replace(
                purchase,
                status=PurchaseStatus.RECEBIDA,
                received_on=datetime.now().isoformat(timespec="seconds"),
            )
