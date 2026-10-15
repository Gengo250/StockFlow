"""Uma alteração de preço ou custo, como a consulta a devolve (H09)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stockflow.domain.enums.price_edit_field import PriceEditField


@dataclass(frozen=True)
class PriceChange:
    """Linha do histórico já resolvida: nomes, não identificadores.

    `old_price` e `new_price` são `Decimal | None` porque a coluna é
    nullable, e a ausência tem significado próprio: informar o custo pela
    primeira vez não tem valor anterior. Trocar isso por `Decimal(0)` aqui
    faria a tela mostrar "De R$ 0,00" — o custo inventado que a coluna
    nullable existe justamente para evitar.

    `product_code` e `product_name` chegam vazios quando o produto foi
    removido: a linha de auditoria sobrevive ao seu alvo, de propósito.
    """

    changed_on: datetime | None
    product_code: str
    product_name: str
    field: PriceEditField
    old_price: Decimal | None
    new_price: Decimal | None
    changed_by: str
