from decimal import Decimal, ROUND_DOWN, localcontext

import pytest

from stockflow.domain.sale_return import (
    OriginalSaleItem, calculate_return_items, return_identifier, return_money,
    validate_return_request, validate_return_stock,
)

SALE = "00000000-0000-0000-0000-000000000001"
ITEM = "00000000-0000-0000-0000-00000000000a"
ITEM2 = "00000000-0000-0000-0000-00000000000b"
ITEM3 = "00000000-0000-0000-0000-00000000000c"


def test_uuid_normalization_detects_case_insensitive_duplicates():
    assert return_identifier(ITEM.upper()) == ITEM
    with pytest.raises(ValueError, match="repetido"):
        validate_return_request(SALE, [(ITEM, 1), (ITEM.upper(), 1)], "Defeito")


@pytest.mark.parametrize("quantity", [True, False, 0, -1, "1", 1.0, 2_147_483_648])
def test_invalid_quantity(quantity):
    with pytest.raises(ValueError):
        validate_return_request(SALE, [(ITEM, quantity)], "Defeito")


@pytest.mark.parametrize("reason", ["", "   ", "\t", "\n", "\r\n", " \t\n\r ", "\v\f"])
def test_reason_requires_non_whitespace_content(reason):
    with pytest.raises(ValueError, match="motivo da devolução"):
        validate_return_request(SALE, [(ITEM, 1)], reason)


@pytest.mark.parametrize("reason", [None, True, 123, []])
def test_reason_must_be_text(reason):
    with pytest.raises(ValueError, match="motivo da devolução"):
        validate_return_request(SALE, [(ITEM, 1)], reason)


@pytest.mark.parametrize("reason,expected", [
    (" Defeito ", "Defeito"),
    ("  Produto com defeito  ", "Produto com defeito"),
    (" \tDefeito\n ", "\tDefeito\n"),
    ("Produto\ncom defeito", "Produto\ncom defeito"),
])
def test_valid_reason_preserves_existing_space_only_normalization(reason, expected):
    sale_id, items, normalized_reason = validate_return_request(SALE, [(ITEM, 1)], reason)
    assert sale_id == SALE
    assert items == ((ITEM, 1),)
    assert normalized_reason == expected


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity", "0.001", "-1", True, None])
def test_invalid_money_is_not_rounded_or_zeroed(amount):
    with pytest.raises(ValueError):
        return_money(amount)


def test_cumulative_rounding_closes_successive_partial_returns():
    original = (OriginalSaleItem(ITEM, "P1", 3, Decimal("1.00")),)
    returned = {}
    amounts = []
    for quantity in (1, 1, 1):
        line, = calculate_return_items(original, Decimal("0.01"), Decimal("2.99"),
                                       ((ITEM, quantity),), returned)
        previous_qty, previous_amount = returned.get(ITEM, (0, Decimal(0)))
        returned[ITEM] = previous_qty + 1, previous_amount + line.subtotal
        amounts.append(line.subtotal)
    assert amounts == [Decimal("1.00"), Decimal("0.99"), Decimal("1.00")]
    assert sum(amounts) == Decimal("2.99")
    line, = calculate_return_items(original, Decimal("0.01"), Decimal("2.99"), ((ITEM, 3),), {})
    assert line.subtotal == sum(amounts)


def test_discount_allocation_is_deterministic_and_conserves_cents():
    original = tuple(OriginalSaleItem(key, key, 1, Decimal("0.01")) for key in (ITEM3, ITEM, ITEM2))
    lines = calculate_return_items(original, Decimal("0.01"), Decimal("0.02"),
                                   ((ITEM2, 1), (ITEM3, 1), (ITEM, 1)), {})
    assert [line.sale_item_id for line in lines] == [ITEM, ITEM2, ITEM3]
    assert [line.subtotal for line in lines] == [Decimal("0.01"), Decimal("0.00"), Decimal("0.01")]
    assert sum(line.discount for line in lines) == Decimal("0.01")


@pytest.mark.parametrize("price,discount,total", [("0", "0", "0"), ("1", "3", "0")])
def test_free_or_fully_discounted_sale(price, discount, total):
    original = (OriginalSaleItem(ITEM, "P1", 3, Decimal(price)),)
    line, = calculate_return_items(original, Decimal(discount), Decimal(total), ((ITEM, 2),), {})
    assert line.subtotal == 0
    assert line.discount == Decimal(price) * 2


def test_values_do_not_depend_on_global_decimal_context():
    original = (OriginalSaleItem(ITEM, "P1", 3, Decimal("1.00")),)
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        line, = calculate_return_items(original, Decimal("0.01"), Decimal("2.99"), ((ITEM, 2),), {})
        assert line.subtotal == Decimal("1.99")


@pytest.mark.parametrize("returned", [{ITEM: (3, Decimal("2.99"))}, {ITEM: (1, Decimal("0.99"))}])
def test_excess_or_inconsistent_history_rejected(returned):
    original = (OriginalSaleItem(ITEM, "P1", 3, Decimal("1.00")),)
    with pytest.raises(ValueError):
        calculate_return_items(original, Decimal("0.01"), Decimal("2.99"), ((ITEM, 1),), returned)


def test_total_must_reconcile_original_prices_and_discount():
    with pytest.raises(ValueError, match="não conciliam"):
        calculate_return_items((OriginalSaleItem(ITEM, "P1", 1, Decimal("10")),),
                               Decimal("1"), Decimal("10"), ((ITEM, 1),), {})


def test_unknown_sale_item_rejected():
    with pytest.raises(ValueError, match="não encontrado"):
        calculate_return_items((OriginalSaleItem(ITEM, "P1", 1, Decimal("10")),),
                               Decimal("0"), Decimal("10"), ((ITEM2, 1),), {})


def test_product_limit_overrides_company_limit_like_sql_coalesce():
    assert validate_return_stock(4, 2, 6, 5) == 6
    assert validate_return_stock(4, 1, None, 5) == 5
    with pytest.raises(ValueError, match="máximo"):
        validate_return_stock(4, 2, None, 5)
    with pytest.raises(ValueError):
        validate_return_stock(2_147_483_647, 1)


@pytest.mark.parametrize("discount,total,expected", [
    ("50", "150", ("50.00", "100.00")),
    ("80", "120", ("40.00", "80.00")),
    ("200", "0", ("0.00", "0.00")),
])
def test_item_discount_stays_on_original_line_and_only_sale_extra_is_allocated(discount, total, expected):
    originals = (
        OriginalSaleItem(ITEM, "P1", 1, Decimal("100"), Decimal("50")),
        OriginalSaleItem(ITEM2, "P2", 1, Decimal("100")),
    )
    lines = calculate_return_items(originals, Decimal(discount), Decimal(total),
                                   ((ITEM2, 1), (ITEM, 1)), {})
    assert tuple(line.subtotal for line in lines) == tuple(map(Decimal, expected))
    assert sum(line.discount for line in lines) == Decimal(discount)


def test_no_discount_defaults_to_zero_and_keeps_legacy_constructor():
    original = (OriginalSaleItem(ITEM, "P1", 3, Decimal("10")),)
    assert original[0].discount_amount == 0
    line, = calculate_return_items(original, None, Decimal("30"), ((ITEM, 2),), {})
    assert line.subtotal == Decimal("20.00")
    assert line.discount == 0


def test_unset_item_discount_is_zero():
    original = (OriginalSaleItem(ITEM, "P1", 1, Decimal("10"), None),)
    line, = calculate_return_items(original, Decimal("0"), Decimal("10"), ((ITEM, 1),), {})
    assert line.subtotal == Decimal("10.00")


def test_all_items_fully_discounted_have_zero_base_without_division():
    original = (OriginalSaleItem(ITEM, "P1", 2, Decimal("10"), Decimal("20")),)
    line, = calculate_return_items(original, Decimal("20"), Decimal("0"), ((ITEM, 1),), {})
    assert line.subtotal == 0
    assert line.discount == Decimal("10.00")


def test_item_and_sale_discount_rounding_closes_successive_returns():
    original = (
        OriginalSaleItem(ITEM, "P1", 3, Decimal("1.00"), Decimal("0.01")),
        OriginalSaleItem(ITEM2, "P2", 1, Decimal("1.00")),
    )
    returned = {}
    amounts = []
    for qty in (1, 1, 1):
        line, = calculate_return_items(original, Decimal("0.03"), Decimal("3.97"),
                                       ((ITEM, qty),), returned)
        old_qty, old_amount = returned.get(ITEM, (0, Decimal(0)))
        returned[ITEM] = old_qty + qty, old_amount + line.subtotal
        amounts.append(line.subtotal)
    assert amounts == [Decimal("0.99"), Decimal("1.00"), Decimal("0.99")]
    other, = calculate_return_items(original, Decimal("0.03"), Decimal("3.97"), ((ITEM2, 1),), returned)
    assert sum(amounts) + other.subtotal == Decimal("3.97")


@pytest.mark.parametrize("item_discount,discount,total", [
    ("11", "11", "9"),  # Desconto de linha maior que o bruto da linha.
    ("5", "4", "16"),   # Cabeçalho menor que a soma dos descontos por item.
    ("-1", "0", "20"), ("NaN", "0", "20"),
])
def test_invalid_item_discount_snapshot_is_rejected(item_discount, discount, total):
    original = (
        OriginalSaleItem(ITEM, "P1", 1, Decimal("10"), Decimal(item_discount)),
        OriginalSaleItem(ITEM2, "P2", 1, Decimal("10")),
    )
    with pytest.raises(ValueError):
        calculate_return_items(original, Decimal(discount), Decimal(total), ((ITEM, 1),), {})


def test_old_incompatible_return_value_is_not_silently_recalculated():
    original = (
        OriginalSaleItem(ITEM, "P1", 2, Decimal("100"), Decimal("100")),
        OriginalSaleItem(ITEM2, "P2", 1, Decimal("100")),
    )
    with pytest.raises(ValueError, match="Histórico"):
        calculate_return_items(original, Decimal("100"), Decimal("200"), ((ITEM, 1),),
                               {ITEM: (1, Decimal("66.67"))})
