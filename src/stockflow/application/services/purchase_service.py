import re

from stockflow.application.dto.purchase_input import (
    PurchaseInput,
    PurchaseItemInput,
)
from stockflow.application.ports.purchase_repository import PurchaseRepository
from stockflow.domain.permissions import ensure_can_manage_purchases


class PurchaseService:
    def __init__(
        self, repository: PurchaseRepository, supplier_repository,
        product_repository,
    ):
        self._repository = repository
        self._supplier_repository = supplier_repository
        self._product_repository = product_repository

    def list_purchases(self, session) -> tuple:
        ensure_can_manage_purchases(session, action="consultar compras")
        return self._repository.list_all()

    def create(self, session, data: PurchaseInput) -> str:
        ensure_can_manage_purchases(session, action="criar compras")
        supplier_id = str(data.supplier_id or "").strip()
        if not supplier_id:
            raise ValueError("Selecione o fornecedor da compra.")
        supplier = self._supplier_repository.get(supplier_id)
        if supplier is None or not supplier.active:
            raise ValueError("Selecione um fornecedor ativo.")
        if not data.items:
            raise ValueError("A compra deve ter pelo menos um item.")

        items = []
        for item in data.items:
            code = str(item.product_code or "").strip()
            if not code:
                raise ValueError("Selecione o produto da compra.")
            if not re.fullmatch(r"[1-9][0-9]*", str(item.quantity).strip()):
                raise ValueError("A quantidade deve ser um inteiro positivo.")
            quantity = int(item.quantity)
            if quantity > 1_000_000:
                raise ValueError("A quantidade por item não pode exceder 1000000.")
            product = self._product_repository.get(code)
            if product is None or not product.active:
                raise ValueError("Selecione um produto ativo.")
            items.append(PurchaseItemInput(code, quantity))

        return self._repository.create(PurchaseInput(supplier_id, tuple(items)))

    def receive(self, session, purchase_id: str) -> None:
        ensure_can_manage_purchases(session, action="receber compras")
        if not str(purchase_id or "").strip():
            raise ValueError("Selecione uma compra para receber.")
        self._repository.receive(str(purchase_id))
