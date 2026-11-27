"""Entrada US30; a chave permanece a mesma ao reenviar a operação."""
from dataclasses import dataclass, field
import re
from uuid import UUID, uuid4

MAX_ITEMS = 100
MAX_QUANTITY = 1_000_000
MAX_REASON_LENGTH = 1000


@dataclass(frozen=True)
class SupplierReturnItemInput:
    product_code: str
    quantity: int
    reason: str


@dataclass(frozen=True)
class SupplierReturnInput:
    supplier_id: str
    items: tuple[SupplierReturnItemInput, ...]
    purchase_id: str | None = None
    idempotency_key: str = field(default_factory=lambda: str(uuid4()))


def normalize_supplier_return(data: SupplierReturnInput) -> SupplierReturnInput:
    if not isinstance(data, SupplierReturnInput):
        raise ValueError("Informe os dados da devolução ao fornecedor.")
    if not isinstance(data.supplier_id, str) or not data.supplier_id.strip():
        raise ValueError("Selecione o fornecedor da devolução.")
    if data.purchase_id is not None and (not isinstance(data.purchase_id, str) or not data.purchase_id.strip()):
        raise ValueError("Informe uma compra de origem válida ou omita o vínculo.")
    try:
        key = str(UUID(str(data.idempotency_key)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Chave da requisição de devolução inválida.") from None
    if not isinstance(data.items, (list, tuple)) or not 1 <= len(data.items) <= MAX_ITEMS:
        raise ValueError("Informe de 1 a 100 itens da devolução.")
    items = []
    for item in data.items:
        if not isinstance(item, SupplierReturnItemInput):
            raise ValueError("Informe itens de devolução válidos.")
        if not isinstance(item.product_code, str) or not item.product_code.strip():
            raise ValueError("Selecione o produto de cada item.")
        if isinstance(item.quantity, bool) or not re.fullmatch(r"[1-9][0-9]*", str(item.quantity)):
            raise ValueError("A quantidade deve ser um inteiro positivo.")
        quantity = int(item.quantity)
        if quantity > MAX_QUANTITY:
            raise ValueError("A quantidade por item não pode exceder 1000000.")
        if not isinstance(item.reason, str) or not item.reason.strip() or len(item.reason) > MAX_REASON_LENGTH:
            raise ValueError("Cada item exige motivo de até 1000 caracteres.")
        items.append(SupplierReturnItemInput(item.product_code.strip(), quantity, item.reason.strip()))
    return SupplierReturnInput(data.supplier_id.strip(), tuple(items),
                               data.purchase_id.strip() if data.purchase_id else None, key)
