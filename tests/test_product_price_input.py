"""Comportamento de entrada monetária no formulário de produtos."""

from stockflow.presentation.widgets.form_fields import _money_input


def test_money_input_uses_brazilian_format_and_database_precision(qapp):
    price_input = _money_input()

    assert price_input.locale().name() == "pt_BR"
    assert price_input.locale().decimalPoint() == ","
    assert price_input.locale().groupSeparator() == "."
    assert price_input.decimals() == 2
    assert price_input.minimum() == 0
    assert price_input.maximum() == 99999999.99
    price_input.setValue(1234.56)
    assert price_input.value() == 1234.56
    assert price_input.textFromValue(price_input.value()) == "1.234,56"
