from datetime import datetime
from uuid import uuid4


def sale_row(sale_id, client_name, product_code, product_name, total, created_on):
    amount = f"{total:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    date = str(created_on)
    try:
        date = datetime.fromisoformat(date.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y %H:%M")
    except ValueError:
        pass
    return {"id": str(sale_id), "cliente": client_name, "produto_codigo": product_code,
            "produto": product_name, "valor": f"R$ {amount}", "data": date,
            "total": str(total)}


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
    def __init__(self, products=None, movements=None):
        from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
        from stockflow.presentation.demo_products import DEMO_PRODUCTS
        self.movements = movements or DemoMovementRepository(
            dict(DEMO_PRODUCTS) if products is None else products
        )
        self.rows = [
            sale_row("VND-1001", "Patrícia Lima", "PRD-004", "Cabo HDMI 2m", 450, "10/08/2026"),
            sale_row("VND-1002", "Ana Ferreira", "PRD-007", "Mouse ergonômico", 1290, "28/09/2026"),
        ]

    def list_all(self):
        return list(self.rows)

    def register(self, client, product, total):
        sale_id = uuid4()
        self.movements.register_sale(sale_id, [{"product": product, "quantity": 1}])
        row = sale_row(sale_id, client.name, product.code, product.name, total,
                       datetime.now().strftime("%d/%m/%Y %H:%M"))
        self.rows.insert(0, row)
        return row

    def register_items(self, client, itens, payment_method, discount, total):
        codigo, descricao = resumo_dos_itens([
            {"product_name": i["product"].name, "product_code": i["product"].code,
             "quantity": i["quantity"]}
            for i in itens
        ])
        sale_id = uuid4()
        self.movements.register_sale(sale_id, itens)
        row = sale_row(sale_id, client.name, codigo, descricao, total,
                       datetime.now().strftime("%d/%m/%Y %H:%M"))
        row.update(payment_method=payment_method, discount=str(discount), status="CONCLUIDA")
        row["items"] = [
            {"product_name": i["product"].name, "product_code": i["product"].code,
             "quantity": i["quantity"]} for i in itens
        ]
        self.rows.insert(0, row)
        return row
