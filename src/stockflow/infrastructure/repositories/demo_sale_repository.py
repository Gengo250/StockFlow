from datetime import datetime
from decimal import Decimal
from threading import RLock
from uuid import uuid4


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
    date = str(created_on)
    try:
        date = (
            datetime.fromisoformat(date.replace("Z", "+00:00"))
            .astimezone()
            .strftime("%d/%m/%Y %H:%M")
        )
    except ValueError:
        pass
    return {
        "id": str(sale_id),
        "cliente": client_name,
        "produto_codigo": ", ".join(product_codes),
        "produto": names,
        "valor": f"R$ {formatted}",
        "data": date,
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
    def __init__(self, products=None, movements=None, movement_repository=None):
        from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
        from stockflow.presentation.demo_products import DEMO_PRODUCTS

        self._products = products if products is not None else dict(DEMO_PRODUCTS)
        self.movements = (
            movement_repository
            or movements
            or DemoMovementRepository(self._products)
        )
        self.rows = [
            sale_row("VND-1001", "Patrícia Lima", ["PRD-004"], ["Cabo HDMI 2m"], 450, "10/08/2026"),
            sale_row("VND-1002", "Ana Ferreira", ["PRD-007"], ["Mouse ergonômico"], 1290, "28/09/2026"),
        ]

    @property
    def movements(self):
        return self._movement_repository

    @movements.setter
    def movements(self, repository):
        self._movement_repository = repository
        self._lock = getattr(repository, "lock", RLock())

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
        movements = self.movements
        sale_id = uuid4()
        with self._lock:
            snapshot_products = {
                item.product_code: inventory[item.product_code]
                for item in items
                if item.product_code in inventory
            }
            snapshot_rows = list(self.rows)
            snapshot_movements = list(movements._movements)
            try:
                movement_items = [
                    {
                        "product": inventory[item.product_code],
                        "quantity": item.quantity,
                    }
                    for item in items
                ]
                movements.register_sale(sale_id, movement_items)
                summary = [
                    {
                        "product_code": item.product_code,
                        "product_name": inventory[item.product_code].name,
                        "quantity": item.quantity,
                    }
                    for item in items
                ]
                code, description = resumo_dos_itens(summary)
                row = sale_row(
                    sale_id,
                    client.name,
                    code,
                    description,
                    total,
                    datetime.now().strftime("%d/%m/%Y %H:%M"),
                    item_count=len(items),
                )
                row["payment_method"] = payment_method
                row["discount"] = str(discount)
                row["status"] = "CONCLUIDA"
                row["items"] = summary
                self.rows.insert(0, row)
                return row
            except Exception:
                for code, product in snapshot_products.items():
                    inventory[code] = product
                self.rows[:] = snapshot_rows
                movements._movements[:] = snapshot_movements
                raise
