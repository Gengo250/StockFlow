from datetime import date, datetime
from copy import deepcopy
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from stockflow.domain.permissions import ensure_can_return_sales
from stockflow.domain.sale_return import (
    OriginalSaleItem,
    calculate_return_items,
    return_identifier,
)
from stockflow.infrastructure.repositories.return_mapper import (
    partial_return_args,
    return_items_from_response,
    return_result_from_response,
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


def data_da_linha(linha):
    """A linha guarda a data já formatada para a tela; o filtro precisa de
    `date`. Aceita os dois formatos que `sale_row` produz."""
    texto = str(linha.get("data", ""))[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _total_da_linha(linha):
    try:
        return Decimal(str(linha.get("total", "0")))
    except Exception:
        return Decimal("0")


#: Chave e sentido por critério, espelhando o `CASE` de `fn_list_sales`. O
#: desempate pelo `id` entra em TODOS porque é o que o banco faz: sem ele a
#: página seguinte repete ou pula linha.
CHAVE_DE_ORDEM = {
    "DATA_DESC": (lambda l: (data_da_linha(l) or date.min, str(l["id"])), True),
    "DATA_ASC": (lambda l: (data_da_linha(l) or date.min, str(l["id"])), False),
    "VALOR_DESC": (lambda l: (_total_da_linha(l), str(l["id"])), True),
    "VALOR_ASC": (lambda l: (_total_da_linha(l), str(l["id"])), False),
    "CLIENTE_ASC": (lambda l: (str(l.get("cliente", "")).casefold(), str(l["id"])), False),
}


class DemoSaleRepository:
    def __init__(
        self, products=None, movements=None, movement_repository=None, *, session=None
    ):
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
        # Estado US20 por instância, independente das sementes de comprovante.
        self._session = session
        self._return_sales = {}
        self._returns = {}
        self._return_requests = {}
        self._product_ids = {}
        # As sementes carregam itens, status e totais porque o comprovante
        # (US19) lê o SNAPSHOT da venda: linha sem item não tem o que
        # comprovar, e a demonstração ficaria sem histórico emitível.
        self.rows = [
            self._semente("VND-1001", "Patrícia Lima", "PRD-004",
                          "Cabo HDMI 2m", 450, "10/08/2026"),
            self._semente("VND-1002", "Ana Ferreira", "PRD-007",
                          "Mouse ergonômico", 1290, "28/09/2026"),
        ]
        self.discount_limits = {"SELLER": Decimal("10.00"), "ADMIN": None}

    @staticmethod
    def _semente(sale_id, cliente, codigo, nome, total, data):
        valor = Decimal(str(total)).quantize(Decimal("0.01"))
        linha = sale_row(sale_id, cliente, [codigo], [nome], valor, data,
                         item_count=1)
        linha.update(
            status="CONCLUIDA",
            payment_method="DINHEIRO",
            discount="0.00",
            original_total=str(valor),
            seller="ana.ferreira",
            items=[{
                "product_code": codigo, "product_name": nome, "quantity": 1,
                "unit_price": str(valor), "subtotal": str(valor),
                "discount_amount": "0.00", "final_subtotal": str(valor),
            }],
        )
        return linha

    def get_discount_limits(self):
        return dict(self.discount_limits)

    def set_discount_limits(self, limits):
        self.discount_limits.update(limits)
        return self.get_discount_limits()

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
        """Histórico defensivo das devoluções registradas no Demo."""
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
                        "quantity_sold": item.quantity,
                        "quantity_returned": qty,
                        "max_returnable": item.quantity - qty,
                    })
            return return_items_from_response(rows)

    def partial_return(self, sale_id, items, reason, idempotency_key):
        ensure_can_return_sales(self._session)
        args = partial_return_args(sale_id, items, reason, idempotency_key)
        sale_id = args["p_sale_id"]
        requested = tuple(
            (item["sale_item_id"], item["quantity"]) for item in args["p_items"]
        )
        with self._lock:
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
                "return_id": return_id,
                "status": "COMPLETED",
                "total_amount": sum((item.subtotal for item in calculated), Decimal(0)),
                "is_total_return": all(
                    returned.get(item.sale_item_id, (0, Decimal(0)))[0]
                    + new_quantities.get(item.sale_item_id, 0) == item.quantity
                    for item in sale["items"]
                ),
            })
            header = {
                **result,
                "company_id": self._session.company_id,
                "sale_id": sale_id,
                "user_id": self._session.user_id,
                "reason": args["p_reason"],
                "created_on": datetime.now(),
                "items": calculated,
            }

            def publish():
                self._returns[return_id] = header
                self._return_requests[request_key] = (deepcopy(args), dict(result))

            committed = False
            try:
                self.movements.register_return(
                    return_id, sale_id, calculated,
                    created_by=self._session.user_id,
                    company_id=self._session.company_id,
                    publish=publish,
                )
                committed = True
                return result
            finally:
                if not committed:
                    self._returns.pop(return_id, None)
                    self._return_requests.pop(request_key, None)

    def _combina(self, linha, filtro):
        """Mesmas regras de `fn_list_sales`, inclusive o período inclusivo.

        Se este método divergir da função SQL, os testes de interface passam
        a validar um comportamento que o banco não tem.
        """
        if filtro.sale_id and not str(linha["id"]).lower().startswith(
            filtro.sale_id.strip().lower()
        ):
            return False
        if filtro.client_id and linha.get("client_id") != filtro.client_id:
            return False
        if filtro.seller_id and linha.get("seller_id") != filtro.seller_id:
            return False
        situacao = linha.get("status", "CONCLUIDA")
        if filtro.status:
            if situacao != filtro.status:
                return False
        elif situacao == "PENDENTE":
            # Sem filtro de status, o histórico mostra vendas finalizadas.
            # Pendentes continuam consultáveis quando selecionadas
            # explicitamente (por exemplo, em registros legados).
            return False
        quando = data_da_linha(linha)
        if filtro.date_from and (quando is None or quando < filtro.date_from):
            return False
        # Inclusivo na tela: "até dia 5" inclui o dia 5 inteiro. O adaptador
        # do Supabase converte para o limite exclusivo que o banco espera.
        if filtro.date_to and (quando is None or quando > filtro.date_to):
            return False
        return True

    def list_page(self, filtro, page, size):
        from stockflow.application.dto.sale_filter import SalePage

        with self._lock:
            linhas = [l for l in self.rows if self._combina(l, filtro)]
        chave, reverso = CHAVE_DE_ORDEM[filtro.sort]
        linhas.sort(key=chave, reverse=reverso)
        inicio = (page - 1) * size
        return SalePage(rows=tuple(linhas[inicio:inicio + size]),
                        total=len(linhas), page=page, size=size)

    def get(self, sale_id):
        with self._lock:
            return next(
                (dict(l) for l in self.rows if str(l["id"]) == str(sale_id)), None
            )

    def cancel(self, sale_id, reason):
        return self._reverter(sale_id, reason, "CANCELAMENTO", "CANCELADA")

    def revert(self, sale_id, reason):
        return self._reverter(sale_id, reason, "DEVOLUCAO", "DEVOLVIDA")

    def _reverter(self, sale_id, reason, kind, status):
        """Devolve o saldo pelo repositório de MOVIMENTAÇÃO, nunca escrevendo
        `Product.stock` direto — o mesmo contrato que o banco impõe."""
        with self._lock:
            linha = next(
                (l for l in self.rows if str(l["id"]) == str(sale_id)), None
            )
            if linha is None:
                raise ValueError("Venda não encontrada.")
            atual = linha.get("status", "CONCLUIDA")
            if atual != "CONCLUIDA":
                # Mesma recusa de `fn_cancel_sale`: reversão é terminal.
                rotulo = "cancelada" if atual == "CANCELADA" else "devolvida"
                raise ValueError(f"Esta venda já foi {rotulo}.")
            self.movements.reverse_sale(sale_id, linha.get("items", []), kind)
            linha.update(
                status=status,
                reversal_kind=kind,
                reversal_reason=reason,
                reversal_on=datetime.now().strftime("%d/%m/%Y %H:%M"),
                reversal_by="Demonstração",
            )
            return dict(linha)

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
        *,
        original_total=None,
        sale_discount_type="FIXED",
        sale_discount_value=Decimal("0"),
        approval_credentials=None,
        seller_id=None,
    ) -> dict:
        authorized_by = None
        if approval_credentials:
            from stockflow.presentation.demo_accounts import autenticar

            approver = autenticar(*approval_credentials)
            if approver is None or approver.role.value != "ADMIN":
                raise ValueError("Credenciais de administrador inválidas.")
            authorized_by = approver.user_id
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
                movements.register_sale(sale_id, movement_items)
                summary = []
                original = Decimal("0.00")
                from stockflow.application.services.sale_service import parse_price
                from stockflow.domain.sale_discount import calculate_discount

                for item in items:
                    product = inventory[item.product_code]
                    unit_price = parse_price(product.sale_price)
                    subtotal = unit_price * item.quantity
                    item_discount = calculate_discount(
                        subtotal, item.discount_type, item.discount_value
                    )
                    summary.append({
                        "id": str(uuid4()),
                        "product_code": item.product_code,
                        "product_name": product.name,
                        "quantity": item.quantity,
                        "unit_price": str(unit_price),
                        "subtotal": str(subtotal),
                        "discount_amount": str(item_discount),
                        "final_subtotal": str(subtotal - item_discount),
                    })
                    original += subtotal
                for item in summary:
                    self._product_ids.setdefault(item["product_code"], str(uuid4()))
                return_snapshot = {
                    "company_id": getattr(self._session, "company_id", None),
                    "status": "CONCLUIDA",
                    "total": Decimal(str(total)),
                    "discount": Decimal(str(discount)),
                    "items": tuple(OriginalSaleItem(
                        item["id"],
                        item["product_code"],
                        item["quantity"],
                        Decimal(item["unit_price"]),
                        Decimal(item["discount_amount"]),
                    ) for item in summary),
                    "names": {item["id"]: item["product_name"] for item in summary},
                    "product_ids": {
                        item["id"]: self._product_ids[item["product_code"]]
                        for item in summary
                    },
                }
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
                row["original_total"] = str(original_total or original)
                row["status"] = "CONCLUIDA"
                row["items"] = summary
                # Mesmos campos que `fn_list_sales` devolve. Sem eles, uma
                # venda recém-registrada não seria encontrada pelo filtro de
                # cliente ou de vendedor, e o modo demonstração divergiria do
                # banco justamente no caminho que o usuário acabou de usar.
                row["client_id"] = getattr(client, "client_id", None)
                row["seller_id"] = seller_id
                from stockflow.presentation.demo_accounts import DEMO_ACCOUNTS

                seller = next(
                    (account for account in DEMO_ACCOUNTS if account.user_id == seller_id),
                    None,
                )
                approver_account = next(
                    (
                        account for account in DEMO_ACCOUNTS
                        if account.user_id == authorized_by
                    ),
                    None,
                )
                row["seller"] = seller.name if seller else ""
                row["discount_applied_by"] = seller_id
                row["discount_applied_by_name"] = seller.name if seller else ""
                row["discount_authorized_by"] = authorized_by
                row["discount_authorized_by_name"] = (
                    approver_account.name if approver_account else ""
                )
                row["reversal_kind"] = None
                row["reversal_reason"] = None
                row["reversal_on"] = None
                row["reversal_by"] = ""
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
                raise
