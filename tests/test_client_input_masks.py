from PySide6.QtTest import QTest

from stockflow.presentation.widgets.client_inputs import (
    ClientDocumentInput,
    ClientPhoneInput,
)


def test_document_input_formats_cpf_as_it_is_typed(qapp):
    field = ClientDocumentInput()
    QTest.keyClicks(field, "52998224725")
    assert field.text() == "529.982.247-25"


def test_document_input_switches_to_cnpj_format(qapp):
    field = ClientDocumentInput()
    QTest.keyClicks(field, "11222333000181")
    assert field.text() == "11.222.333/0001-81"


def test_document_input_formats_existing_unpunctuated_document(qapp):
    field = ClientDocumentInput("52998224725")
    assert field.text() == "529.982.247-25"


def test_phone_input_formats_landline_as_it_is_typed(qapp):
    field = ClientPhoneInput()
    QTest.keyClicks(field, "1133334444")
    assert field.text() == "(11) 3333-4444"


def test_phone_input_formats_mobile_as_it_is_typed(qapp):
    field = ClientPhoneInput()
    QTest.keyClicks(field, "11998887766")
    assert field.text() == "(11) 99888-7766"


def test_phone_input_formats_existing_unpunctuated_number(qapp):
    field = ClientPhoneInput("11998887766")
    assert field.text() == "(11) 99888-7766"
