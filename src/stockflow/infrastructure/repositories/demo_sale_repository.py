from datetime import datetime
from uuid import uuid4


def sale_row(sale_id, client_name, product_code, product_name, total, created_on):
    amount = f"{total:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return {"id": str(sale_id), "cliente": client_name, "produto_codigo": product_code,
            "produto": product_name, "valor": f"R$ {amount}", "data": str(created_on),
            "total": str(total)}


class DemoSaleRepository:
    def __init__(self):
        self.rows = [
            sale_row("VND-1001", "Patrícia Lima", "PRD-004", "Cabo HDMI 2m", 450, "10/08/2026"),
            sale_row("VND-1002", "Ana Ferreira", "PRD-007", "Mouse ergonômico", 1290, "28/09/2026"),
        ]

    def list_all(self):
        return list(self.rows)

    def register(self, client, product, total):
        row = sale_row(uuid4(), client.name, product.code, product.name, total,
                       datetime.now().strftime("%d/%m/%Y %H:%M"))
        self.rows.insert(0, row)
        return row
