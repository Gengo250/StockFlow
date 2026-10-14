from datetime import datetime
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from stockflow.domain.stock_level import derive_stock_status, to_int


def sale_row(sale_id, client_name, product_codes, product_names, total, created_on):
    if isinstance(product_codes, str):
        product_codes = [part.strip() for part in product_codes.split(",") if part.strip()]
    if isinstance(product_names, str):
        product_names = [part.strip() for part in product_names.split(",") if part.strip()]
    product_codes = list(product_codes)
    product_names = list(product_names)
    amount = Decimal(str(total)).quantize(Decimal("0.01"))
    formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    names = ", ".join(product_names)
    return {
        "id": str(sale_id),
        "cliente": client_name,
        "produto_codigo": ", ".join(product_codes),
        "produto": names,
        "valor": f"R$ {formatted}",
        "data": str(created_on),
        "total": str(amount),
        "itens_count": len(product_codes),
    }


class DemoSaleRepository:
    def __init__(self, products=None, movement_repository=None):
        self._products = products if products is not None else {}
        self._movement_repository = movement_repository
        self._lock = (
            movement_repository.lock
            if movement_repository is not None
            else RLock()
        )
        self.rows = [
            sale_row("VND-1001", "Patrícia Lima", ["PRD-004"], ["Cabo HDMI 2m"], 450, "10/08/2026"),
            sale_row("VND-1002", "Ana Ferreira", ["PRD-007"], ["Mouse ergonômico"], 1290, "28/09/2026"),
        ]

    def list_all(self):
        with self._lock:
            return list(self.rows)

    def register_multiple(self, client, items: tuple, total: Decimal) -> dict:
        inventory = self._products
        movements = self._movement_repository
        with self._lock:
            touched_codes = {item.product_code for item in items}
            snapshot_products = {
                code: inventory[code] for code in touched_codes
            }
            snapshot_rows = list(self.rows)
            snapshot_movements = (
                list(movements._movements) if movements is not None else None
            )
            try:
                if movements is not None:
                    movements.register_sale(items)
                else:
                    self._apply_stock(items, inventory)
                row = sale_row(
                    uuid4(),
                    client.name,
                    [item.product_code for item in items],
                    [inventory[item.product_code].name for item in items],
                    total,
                    datetime.now().strftime("%d/%m/%Y %H:%M"),
                )
                self.rows.insert(0, row)
                return row
            except Exception:
                for code, product in snapshot_products.items():
                    inventory[code] = product
                self.rows[:] = snapshot_rows
                if movements is not None:
                    movements._movements[:] = snapshot_movements
                raise

    @staticmethod
    def _apply_stock(items, products):
        import dataclasses

        quantities = {}
        for item in items:
            quantities[item.product_code] = quantities.get(item.product_code, 0) + item.quantity
        updated = {}
        for code, quantity in quantities.items():
            product = products[code]
            stock = to_int(product.stock)
            if quantity > stock:
                raise ValueError(
                    f"Estoque insuficiente para o produto {code}: "
                    f"solicitado {quantity}, disponível {stock}."
                )
            remaining = stock - quantity
            updated[code] = dataclasses.replace(
                product,
                stock=str(remaining),
                stock_status=derive_stock_status(remaining, product.minimum_stock),
            )
        products.update(updated)
