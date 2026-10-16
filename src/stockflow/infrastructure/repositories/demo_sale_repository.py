from datetime import datetime
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from stockflow.domain.stock_level import derive_stock_status, to_int


def sale_row(
    sale_id, client_name, product_codes, product_names, total, created_on,
    item_count=None,
):
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
        "itens_count": len(product_codes) if item_count is None else item_count,
    }


def resumo_dos_itens(itens):
    """Reduz os itens de uma venda ao par (código, descrição) da listagem.

    O histórico tem uma linha por VENDA, não por item, e a coluna "Produto"
    tem largura de nome de produto. Com um item só a linha continua idêntica
    ao que a tela mostrava quando venda era sinônimo de produto; com vários,
    o código perde sentido e sai de cena, porque não existe "o" código de uma
    venda de três produtos.
    """
    if not itens:
        return "", "—"
    if len(itens) == 1:
        item = itens[0]
        nome = item["product_name"]
        if int(item.get("quantity", 1)) > 1:
            nome = f"{int(item['quantity'])}x {nome}"
        return item["product_code"], nome
    return "", f"{len(itens)} itens"


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

    def register(self, client, product, total):
        from stockflow.application.dto.sale_item import SaleItemInput

        return self.register_multiple(
            client, (SaleItemInput(product.code, 1),), total
        )

    def register_items(self, client, itens, payment_method, discount, total):
        from stockflow.application.dto.sale_item import SaleItemInput

        items = tuple(
            SaleItemInput(item["product"].code, item["quantity"])
            for item in itens
        )
        return self.register_multiple(
            client, items, total, payment_method, discount
        )

    def register_multiple(
        self,
        client,
        items: tuple,
        total: Decimal,
        payment_method="DINHEIRO",
        discount=Decimal("0"),
    ) -> dict:
        inventory = self._products
        movements = self._movement_repository
        with self._lock:
            touched_codes = {
                item.product_code for item in items if item.product_code in inventory
            }
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
                elif inventory:
                    self._apply_stock(items, inventory)
                summary = [
                    {
                        "product_code": item.product_code,
                        "product_name": inventory[item.product_code].name
                        if item.product_code in inventory
                        else item.product_code,
                        "quantity": item.quantity,
                    }
                    for item in items
                ]
                code, description = resumo_dos_itens(summary)
                row = sale_row(
                    uuid4(),
                    client.name,
                    code,
                    description,
                    total,
                    datetime.now().strftime("%d/%m/%Y %H:%M"),
                    item_count=len(items),
                )
                row["payment_method"] = payment_method
                row["discount"] = str(discount)
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
