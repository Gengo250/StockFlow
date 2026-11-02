"""Exemplos integrados da janela desktop, recriados a cada sessão local.

Os repositórios isolados mantêm suas fixtures pequenas. Aqui os exemplos de
venda passam pelas mesmas operações de estoque usadas durante a sessão.
"""

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.application.dto.movement_input import MovementInput
from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.application.services.sale_service import parse_price
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
from stockflow.presentation.demo_accounts import conta_admin


def populate_demo_operations(products, clients, sales, movements):
    """Adiciona exemplos com vínculo venda/movimento e preserva o saldo inicial.

    As entradas de abertura incluem as quantidades vendidas nos exemplos.
    Assim, os saldos finais continuam cobrindo os estados de alerta do catálogo.
    Cada janela tem seu próprio catálogo e seus próprios repositórios.
    """
    # Fontes injetadas (inclusive indisponíveis) não recebem gravações de
    # exemplo. Só os adaptadores locais concretos pertencem a esta montagem.
    if not isinstance(sales, DemoSaleRepository) or not isinstance(movements, DemoMovementRepository):
        return
    now = datetime.now()
    seller = conta_admin()
    examples = (
        ("CLI-001", (("PRD-009", 1), ("PRD-008", 2)), "PIX", "20.00", None, 1),
        ("CLI-002", (("PRD-005", 2),), "DEBITO", "0.00", None, 2),
        ("CLI-004", (("PRD-003", 2),), "DINHEIRO", "0.00", None, 3),
        ("CLI-006", (("PRD-007", 1),), "CREDITO", "0.00", "cancel", 4),
        ("CLI-008", (("PRD-009", 1),), "PIX", "0.00", "revert", 5),
    )
    examples = [example for example in examples
                if clients.get(example[0]) is not None
                and all(code in products and products[code].active
                        for code, _ in example[1])]
    sold = {}
    for _, items, _, _, reversal, _ in examples:
        if reversal is None:
            for code, quantity in items:
                sold[code] = sold.get(code, 0) + quantity

    # Saldo de abertura rastreável, sem alterar os objetos globais DEMO_PRODUCTS.
    for code, product in tuple(products.items()):
        if not product.active:
            continue
        opening = int(product.stock) + sold.get(code, 0)
        products[code] = replace(product, stock="0")
        if opening:
            movements.register(MovementInput(
                code, MovementKind.ENTRADA, opening,
                note="Saldo de abertura da demonstração", supplier_id="FOR-001",
                confirm=True,
            ))

    for client_id, selections, payment, discount, reversal, days in reversed(examples):
        items = tuple(SaleItemInput(code, quantity) for code, quantity in selections)
        original = sum((parse_price(products[code].sale_price) * quantity
                        for code, quantity in selections), Decimal("0.00"))
        discount = Decimal(discount)
        row = sales.register_multiple(
            clients.get(client_id), items, original - discount,
            payment, discount, original_total=original, seller_id=seller.user_id,
        )
        row["data"] = (now - timedelta(days=days)).strftime("%d/%m/%Y %H:%M")
        if reversal:
            reason = ("Exemplo: lançamento em duplicidade" if reversal == "cancel"
                      else "Exemplo: cliente devolveu o produto")
            getattr(sales, reversal)(row["id"], reason)

    if "PRD-008" in products and products["PRD-008"].active:
        movements.register(MovementInput(
            "PRD-008", MovementKind.ENTRADA, 12,
            note="Reposição aguardando conferência", supplier_id="FOR-001",
        ))
    if "PRD-005" in products and products["PRD-005"].active:
        cancelled = movements.register(MovementInput(
            "PRD-005", MovementKind.SAIDA, 1, note="Reserva cancelada pelo cliente",
        ))
        movements.cancel(cancelled)
        balance = int(products["PRD-005"].stock)
        movements.register(MovementInput(
            "PRD-005", MovementKind.ENTRADA, 1, confirm=True,
            supplier_id="FOR-001", note="Conferência de recebimento",
        ))
        movements.adjust(AdjustmentInput(
            product_code="PRD-005", counted_balance=balance,
            reason=AdjustmentReason.CONTAGEM,
            detail="Exemplo: correção após inventário", expected_balance=balance + 1,
        ))
