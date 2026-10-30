from datetime import datetime
from copy import deepcopy
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from stockflow.domain.permissions import ensure_can_return_sales
from stockflow.domain.sale_return import (
    OriginalSaleItem, calculate_return_items, return_identifier,
)
from stockflow.infrastructure.repositories.return_mapper import (
    partial_return_args, return_items_from_response, return_result_from_response,
)


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
    def __init__(self, products=None, movements=None, movement_repository=None, *, session=None):
        from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
        from stockflow.presentation.demo_products import DEMO_PRODUCTS

        repositorio = movement_repository or movements
        if products is not None:
            self._products = products
        elif repositorio is not None:
            # Sem isto o repositório de vendas ficava com uma CÓPIA de
            # DEMO_PRODUCTS enquanto o de movimentação baixava estoque noutro
            # dict. As duas visões divergiam em silêncio: a venda gravava
            # nomes velhos e o rollback restaurava os objetos errados.
            self._products = getattr(repositorio, "products", None) or dict(DEMO_PRODUCTS)
        else:
            self._products = dict(DEMO_PRODUCTS)
        self.movements = repositorio or DemoMovementRepository(self._products)
        self._session = session
        self._return_sales = {}
        self._returns = {}
        # Índice do Demo, não substitui a unicidade persistida pelo PostgreSQL.
        self._return_requests = {}
        self._product_ids = {}
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

    @property
    def returns(self) -> tuple[dict, ...]:
        """Histórico próprio; não expor dicionários internos mutáveis."""
        with self._lock:
            return tuple(deepcopy(list(self._returns.values())))

    def _sale_for_return(self, sale_id, *, require_concluded=True):
        sale = self._return_sales.get(sale_id)
        if sale is None:
            if any(str(row["id"]) == sale_id for row in self.rows):
                raise ValueError("Venda sem snapshot confiável para devolução.")
            raise LookupError("Venda não encontrada ou sem snapshot para devolução.")
        if sale["company_id"] != self._session.company_id:
            from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
            raise PermissionDeniedError("registrar devoluções", self._session.role)
        if require_concluded and sale["status"] != "CONCLUIDA":
            raise ValueError("Somente venda concluída pode ser devolvida.")
        return sale

    def _returned_items(self, sale_id):
        result = {}
        for header in self._returns.values():
            if (header["sale_id"] != sale_id or header["status"] != "COMPLETED"
                    or header["company_id"] != self._session.company_id):
                continue
            for item in header["items"]:
                qty, amount = result.get(item.sale_item_id, (0, Decimal(0)))
                result[item.sale_item_id] = (qty + item.quantity, amount + item.subtotal)
        return result

    def get_returnable_items(self, sale_id: str) -> list[dict]:
        ensure_can_return_sales(self._session, "consultar itens devolvíveis")
        sale_id = return_identifier(sale_id)
        with self._lock:
            sale = self._sale_for_return(sale_id)
            returned = self._returned_items(sale_id)
            rows = []
            for item in sorted(sale["items"], key=lambda item: item.sale_item_id):
                qty, _ = returned.get(item.sale_item_id, (0, Decimal(0)))
                if qty < item.quantity:
                    rows.append({
                        "sale_item_id": item.sale_item_id,
                        "product_id": sale["product_ids"][item.sale_item_id]
                        if item.product_code in self._products else None,
                        "product_name": sale["names"][item.sale_item_id],
                        "quantity_sold": item.quantity, "quantity_returned": qty,
                        "max_returnable": item.quantity - qty,
                    })
            return return_items_from_response(rows)

    def partial_return(self, sale_id, items, reason, idempotency_key):
        ensure_can_return_sales(self._session)
        args = partial_return_args(sale_id, items, reason, idempotency_key)
        sale_id = args["p_sale_id"]
        requested = tuple((item["sale_item_id"], item["quantity"]) for item in args["p_items"])
        with self._lock:
            # Como na RPC, autorizar a venda antes de recuperar a resposta; não
            # revalidar saldo/status/produto de uma operação já confirmada.
            self._sale_for_return(sale_id, require_concluded=False)
            request_key = (self._session.company_id, args["p_idempotency_key"])
            previous = self._return_requests.get(request_key)
            if previous is not None:
                original_args, original_result = previous
                if original_args != args:
                    raise ValueError("Chave de idempotência reutilizada com conteúdo diferente.")
                return dict(original_result)
            if self.movements.products is not self._products:
                raise RuntimeError("Vendas e movimentos devem compartilhar o mesmo catálogo Demo.")
            sale = self._sale_for_return(sale_id)
            returned = self._returned_items(sale_id)
            calculated = calculate_return_items(
                sale["items"], sale["discount"], sale["total"], requested, returned
            )
            return_id = str(uuid4())
            new_quantities = {item.sale_item_id: item.quantity for item in calculated}
            result = return_result_from_response({
                "return_id": return_id, "status": "COMPLETED",
                "total_amount": sum((item.subtotal for item in calculated), Decimal(0)),
                "is_total_return": all(
                    returned.get(item.sale_item_id, (0, Decimal(0)))[0]
                    + new_quantities.get(item.sale_item_id, 0) == item.quantity
                    for item in sale["items"]
                ),
            })
            header = {
                **result, "company_id": self._session.company_id, "sale_id": sale_id,
                "user_id": self._session.user_id, "reason": args["p_reason"],
                "created_on": datetime.now(), "items": calculated,
            }

            def publish():
                self._returns[return_id] = header
                self._return_requests[request_key] = (deepcopy(args), dict(result))

            committed = False
            try:
                self.movements.register_return(
                    return_id, sale_id, calculated, created_by=self._session.user_id,
                    company_id=self._session.company_id,
                    publish=publish,
                )
                committed = True
                return result
            finally:
                if not committed:
                    self._returns.pop(return_id, None)
                    self._return_requests.pop(request_key, None)

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
            # O `in inventory` logo abaixo já admitia que o código pode faltar,
            # mas as leituras seguintes indexavam direto: um produto retirado
            # do catálogo entre a seleção e a confirmação virava
            # `KeyError: 'PRD-007'`, que a tela mostrava cru no aviso.
            ausentes = [i.product_code for i in items if i.product_code not in inventory]
            if ausentes:
                raise ValueError("Selecione um produto ativo válido.")
            snapshot_products = {
                item.product_code: inventory[item.product_code]
                for item in items
                if item.product_code in inventory
            }
            snapshot_rows = list(self.rows)
            try:
                movement_items = [
                    {
                        "product": inventory[item.product_code],
                        "quantity": item.quantity,
                    }
                    for item in items
                ]
                from stockflow.application.services.sale_service import parse_price
                summary = [
                    {
                        "id": str(uuid4()),
                        "product_code": item.product_code,
                        "product_name": inventory[item.product_code].name,
                        "quantity": item.quantity,
                        "unit_price": str(parse_price(inventory[item.product_code].sale_price)),
                        "subtotal": str(parse_price(inventory[item.product_code].sale_price) * item.quantity),
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
                # Snapshot separado da linha exposta à UI: mudanças de catálogo
                # ou de apresentação não alteram o preço/desconto original.
                for item in summary:
                    self._product_ids.setdefault(item["product_code"], str(uuid4()))
                return_snapshot = {
                    "company_id": getattr(self._session, "company_id", None),
                    "status": "CONCLUIDA", "total": Decimal(str(total)),
                    "discount": Decimal(str(discount)),
                    "items": tuple(OriginalSaleItem(
                        item["id"], item["product_code"], item["quantity"], Decimal(item["unit_price"])
                    ) for item in summary),
                    "names": {item["id"]: item["product_name"] for item in summary},
                    "product_ids": {item["id"]: self._product_ids[item["product_code"]] for item in summary},
                }
                # Toda conversão nova ocorre ANTES da baixa atômica existente.
                movements.register_sale(sale_id, movement_items)
                self.rows.insert(0, row)
                self._return_sales[str(sale_id)] = return_snapshot
                return row
            except Exception:
                for code, product in snapshot_products.items():
                    inventory[code] = product
                # `movements.register_sale` já desfaz o que escreveu, sob o
                # mesmo lock. Refazer o rollback aqui, lendo e reescrevendo a
                # lista privada dele, só acrescentava a chance de apagar
                # movimentação alheia -- e quebrava com qualquer repositório
                # de movimentação que não tivesse esse atributo.
                self.rows[:] = snapshot_rows
                self._return_sales.pop(str(sale_id), None)
                raise
