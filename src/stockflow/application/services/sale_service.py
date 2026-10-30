"""Registro comercial; a conclusão baixa o estoque na mesma operação."""

from decimal import Decimal, InvalidOperation
import re

from stockflow.application.dto.sale_item import SaleItemInput, SaleItemValidator
from stockflow.application.dto.sale_filter import (
    MOTIVO_MAXIMO, TAMANHO_MAXIMO, TAMANHO_PADRAO, SaleFilter,
)
from stockflow.domain.enums.operation_kind import OperationKind
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.permissions import (
    ensure_can_register_sales, ensure_can_reverse_sales,
    ensure_can_manage_companies, exigir_ver,
)
from stockflow.domain.product_status import ensure_product_selectable
from stockflow.domain.sale_discount import (
    DiscountKind, calculate_discount, calculate_discount_breakdown,
)

_LEGACY_LIST = object()

_MONEY_PATTERN = re.compile(
    r"(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?|\d+\.\d{1,2}"
)

# Espelha public.payment_method (database/code/tables/06_clients_sales.sql).
# Rótulo que não existe lá seria recusado pelo banco com erro de tipo, que não
# diz ao operador qual é a forma válida.
FORMAS_DE_PAGAMENTO = ("DINHEIRO", "DEBITO", "CREDITO", "PIX", "VALE", "OUTRO")

# A recusa do carrinho vazio nasce aqui e em nenhum outro lugar. Ela já existiu
# em quatro redações ao mesmo tempo -- tela, serviço, banco e teste -- e a
# suíte ficou vermelha porque duas delas se contradiziam. Carrinho vazio não é
# produto inválido: a tela que importar esta constante aponta o campo certo.
SEM_ITENS = "Adicione pelo menos um item à venda."


class DiscountApprovalRequired(ValueError):
    """O desconto exige autenticação de ADMIN antes da gravação."""


def parse_total(value) -> Decimal:
    """Converte um preço brasileiro ou decimal para centavos exatos."""
    text = str(value).strip()
    if text.upper().startswith("R$"):
        text = text[2:].strip()
    if not _MONEY_PATTERN.fullmatch(text):
        # Esta função também parseia o DESCONTO (`vendas.py` e
        # `register_multiple`). Nomear o preço mandava o operador
        # conferir um campo que ele não tinha tocado, e a mensagem
        # deixava de dizer o que é um valor válido.
        raise ValueError("Informe um valor válido, com até duas casas decimais.")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("Valor da venda inválido.") from error
    if not amount.is_finite() or amount < 0 or amount >= Decimal("100000000"):
        raise ValueError("Valor da venda inválido.")
    return amount.quantize(Decimal("0.01"))


def calculate_total_from_items(
    items: tuple[SaleItemInput, ...],
    product_codes_to_prices: dict[str, Decimal],
) -> Decimal:
    """Calcula o total exclusivamente com os preços vigentes do catálogo."""
    return sum(
        (
            product_codes_to_prices[item.product_code] * item.quantity
            for item in items
        ),
        start=Decimal("0.00"),
    ).quantize(Decimal("0.01"))


def parse_price(value) -> Decimal:
    """Preço do catálogo ("R$ 2.499,90") como Decimal."""
    return parse_total(str(value).replace("R$", "").strip())


def parse_quantity(value) -> int:
    text = str(value).strip()
    if not re.fullmatch(r"\d+", text) or int(text) <= 0:
        raise ValueError("Informe uma quantidade inteira maior que zero.")
    quantidade = int(text)
    if quantidade > 1_000_000:
        raise ValueError("Quantidade acima do limite por item.")
    return quantidade


class SaleService:
    def __init__(self, repository, clients, products):
        self.repository, self.clients, self.products = repository, clients, products

    def _cliente_ativo(self, client_id):
        client = self.clients.get(client_id)
        if client is None or not client.active:
            raise ValueError("Selecione um cliente ativo válido.")
        return client

    def _produto_ativo(self, product_code):
        product = self.products.get(product_code)
        if product is None or not product.active:
            raise ValueError("Selecione um produto ativo válido.")
        return product

    def register(self, session, client_id, product_code, value):
        ensure_can_register_sales(session)
        total = parse_total(value)
        client = self._cliente_ativo(client_id)
        product = self._produto_ativo(product_code)
        return self.repository.register(client, product, total)

    def register_sale(self, session, client_id, itens,
                      payment_method="DINHEIRO", discount="0",
                      discount_type="FIXED", approval_credentials=None):
        """Venda com vários itens, forma de pagamento e desconto (US10).

        `itens` são pares código/quantidade. O preço NÃO vem daqui: o total
        calculado nesta camada é o que a tela mostra. O repositório envia
        códigos, quantidades e instruções de desconto; a RPC relê os preços
        do catálogo na mesma transação que valida e baixa o estoque.
        """
        ensure_can_register_sales(session)

        if not itens:
            raise ValueError(SEM_ITENS)
        if payment_method not in FORMAS_DE_PAGAMENTO:
            raise ValueError("Selecione uma forma de pagamento válida.")
        for item in itens:
            self._produto_ativo(item["codigo"])

        normalized_items = tuple(
            SaleItemInput(
                product_code=item["codigo"],
                quantity=parse_quantity(item["quantidade"]),
                discount_type=item.get("discount_type", "FIXED"),
                discount_value=self._parse_discount_value(
                    item.get("discount_value", "0"), item.get("discount_type", "FIXED")
                ),
            )
            for item in itens
        )
        return self.register_multiple(
            session, client_id, normalized_items, payment_method, discount,
            discount_type, approval_credentials,
        )

    def list_sales(self, session=_LEGACY_LIST, filtro=None, page=1, size=TAMANHO_PADRAO):
        # Compatibilidade temporária com a UI local pré-US17. Não habilita o
        # caminho paginado sem sessão, nem transforma sessão inválida em legado.
        if session is _LEGACY_LIST:
            if filtro is not None or page != 1 or size != TAMANHO_PADRAO:
                raise ValueError("Informe a sessão para consultar o histórico paginado.")
            return self.repository.list_all()
        exigir_ver(session, "vendas", "consultar o histórico de vendas")
        if type(page) is not int or page < 1:
            raise ValueError("Página inválida.")
        if type(size) is not int or not 1 <= size <= TAMANHO_MAXIMO:
            raise ValueError(f"Tamanho de página inválido: use entre 1 e {TAMANHO_MAXIMO}.")
        return self.repository.list_page(filtro or SaleFilter(), page, size)

    def get_sale(self, session, sale_id):
        exigir_ver(session, "vendas", "consultar o histórico de vendas")
        if not sale_id:
            raise ValueError("Não foi possível identificar a venda.")
        return self.repository.get(sale_id)

    def cancel_sale(self, session, sale_id, reason):
        ensure_can_reverse_sales(session, action="cancelar vendas")
        return self.repository.cancel(sale_id, self._motivo(reason))

    def return_sale(self, session, sale_id, reason):
        ensure_can_reverse_sales(session, action="devolver vendas")
        return self.repository.revert(sale_id, self._motivo(reason))

    @staticmethod
    def _motivo(reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Informe o motivo da operação.")
        text = reason.strip()
        if len(text) > MOTIVO_MAXIMO:
            raise ValueError(f"O motivo deve ter no máximo {MOTIVO_MAXIMO} caracteres.")
        return text

    def register_multiple(
        self,
        session,
        client_id,
        items: tuple[SaleItemInput, ...],
        payment_method="DINHEIRO",
        discount="0",
        discount_type="FIXED",
        approval_credentials=None,
    ) -> dict:
        ensure_can_register_sales(session)

        if not items:
            raise ValueError(SEM_ITENS)
        if payment_method not in FORMAS_DE_PAGAMENTO:
            raise ValueError("Selecione uma forma de pagamento válida.")
        client = self._cliente_ativo(client_id)

        normalized_items = tuple(SaleItemInput(
            item.product_code, item.quantity, DiscountKind(item.discount_type).value,
            self._parse_discount_value(item.discount_value, item.discount_type),
        ) for item in items)
        item_validator = SaleItemValidator(self.products)
        item_validator.validate(normalized_items)

        products_by_code = {}
        prices_by_code = {}
        for item in normalized_items:
            if item.product_code not in products_by_code:
                product = self.products.get(item.product_code)
                if product is None:
                    raise ValueError(f"Produto {item.product_code} não existe.")
                ensure_product_selectable(
                    product, OperationKind.VENDA, code=item.product_code
                )
                products_by_code[item.product_code] = product
                prices_by_code[item.product_code] = parse_total(product.sale_price)

        bruto = calculate_total_from_items(normalized_items, prices_by_code)
        if bruto >= Decimal("100000000"):
            raise ValueError("Total da venda acima do limite de R$ 99.999.999,99.")
        descontos_itens = tuple(calculate_discount(
            prices_by_code[item.product_code] * item.quantity,
            item.discount_type, item.discount_value,
        ) for item in normalized_items)
        base_desconto_venda = bruto - sum(descontos_itens, Decimal("0.00"))
        valor_desconto_venda = self._parse_discount_value(discount or "0", discount_type)
        desconto_venda = calculate_discount(base_desconto_venda, discount_type, valor_desconto_venda)
        resumo = calculate_discount_breakdown(bruto, descontos_itens, desconto_venda)
        get_limits = getattr(self.repository, "get_discount_limits", None)
        if callable(get_limits):
            limites = get_limits()
            role = UserRole.from_value(session.role)
            limite = limites.get(role.value)
            if limite is not None and resumo.effective_percent > Decimal(str(limite)):
                if not approval_credentials:
                    raise DiscountApprovalRequired(
                        "Este desconto excede o limite do vendedor e exige "
                        "autorização de um administrador."
                    )
            return self.repository.register_multiple(
                client, normalized_items, resumo.net, payment_method, resumo.total_discount,
                original_total=resumo.gross,
                sale_discount_type=DiscountKind(discount_type).value,
                sale_discount_value=valor_desconto_venda,
                approval_credentials=approval_credentials,
                seller_id=getattr(session, "user_id", None),
            )
        # Adaptador anterior à US22: preservar somente o contrato já suportado.
        # Nunca descartar descontos por item, percentual ou pedido de aprovação.
        if (any(item.discount_value != 0 for item in normalized_items)
                or DiscountKind(discount_type) is not DiscountKind.FIXED
                or approval_credentials is not None):
            raise ValueError("Este repositório não suporta o fluxo de descontos US22.")
        # The repository owns the transaction boundary. In particular, stock
        # changes are never performed as a second write after this returns.
        return self.repository.register_multiple(
            client, normalized_items, resumo.net, payment_method, resumo.total_discount
        )

    @staticmethod
    def _parse_discount_value(value, discount_type):
        try:
            kind = DiscountKind(discount_type)
        except ValueError as error:
            raise ValueError("Selecione um tipo de desconto válido.") from error
        amount = parse_total(value or "0")
        if kind is DiscountKind.PERCENTAGE and amount > Decimal("100"):
            raise ValueError("O desconto percentual deve estar entre 0% e 100%.")
        return amount

    def get_discount_limits(self, session):
        ensure_can_manage_companies(session, action="consultar limites de desconto")
        return self.repository.get_discount_limits()

    def set_discount_limits(self, session, seller_limit):
        ensure_can_manage_companies(session, action="alterar limites de desconto")
        limit = parse_total(seller_limit)
        if limit > Decimal("100"):
            raise ValueError("O limite de desconto deve estar entre 0% e 100%.")
        return self.repository.set_discount_limits({"SELLER": limit})
