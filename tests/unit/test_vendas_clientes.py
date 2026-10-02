"""US: página de vendas e associação de clientes (commit af9fb43)."""

import pytest

from stockflow.presentation.pages.vendas import VendasPage


@pytest.fixture
def page(qapp):
    return VendasPage()


def combo_names(page):
    return [
        page.cliente_combo.itemData(i)["nome"]
        for i in range(page.cliente_combo.count())
        if page.cliente_combo.itemData(i)
    ]


def table_clients(page):
    return [page.table.item(r, 1).text() for r in range(page.table.rowCount())]


def test_combo_lista_somente_clientes_ativos(page):
    assert combo_names(page) == ["Ana Ferreira", "Carlos Mendes", "Juliana Ramos"]
    assert "Patrícia Lima" not in combo_names(page)


def test_primeiro_item_do_combo_e_placeholder_sem_dado(page):
    assert page.cliente_combo.itemText(0) == "Selecione um cliente..."
    assert page.cliente_combo.itemData(0) is None


def test_historico_inicial_preserva_cliente_hoje_inativo(page):
    assert table_clients(page) == ["Patrícia Lima", "Ana Ferreira"]


def test_selecionar_cliente_externo_ativo(page):
    assert page.selecionar_cliente_externo("Carlos Mendes") is True
    assert page.cliente_combo.currentData()["id"] == "CLI-002"
    assert page.warning_label.text() == ""


def test_selecionar_cliente_externo_inativo_bloqueia_e_avisa(page):
    assert page.selecionar_cliente_externo("Patrícia Lima") is False
    assert page.cliente_combo.currentData() is None
    assert "inativo" in page.warning_label.text().lower()


def test_registrar_venda_valida_cliente(page):
    page.val_input.setText("100,00")
    page._registrar_venda()
    assert page.warning_label.text() == "Selecione um cliente ativo válido."
    assert page.table.rowCount() == 2


def test_registrar_venda_valida_valor(page):
    page.selecionar_cliente_externo("Ana Ferreira")
    page.val_input.setText("   ")
    page._registrar_venda()
    assert page.warning_label.text() == "Informe o valor da venda."
    assert page.table.rowCount() == 2


def test_registrar_venda_insere_no_topo_do_historico(page):
    page.selecionar_cliente_externo("Juliana Ramos")
    page.val_input.setText("320,50")
    page._registrar_venda()

    assert page.table.rowCount() == 3
    assert page.table.item(0, 1).text() == "Juliana Ramos"
    assert page.table.item(0, 2).text() == "R$ 320,50"
    assert page.table.item(0, 0).text() == "VND-1003"


def test_registrar_venda_limpa_formulario(page):
    page.selecionar_cliente_externo("Ana Ferreira")
    page.val_input.setText("10,00")
    page._registrar_venda()

    assert page.val_input.text() == ""
    assert page.cliente_combo.currentIndex() == 0
    assert page.warning_label.text() == ""


def test_trocar_cliente_limpa_alerta_anterior(page):
    page.selecionar_cliente_externo("Patrícia Lima")
    assert page.warning_label.text() != ""
    page.selecionar_cliente_externo("Ana Ferreira")
    assert page.warning_label.text() == ""


def test_id_de_venda_permanece_unico_apos_varias_vendas(page):
    for i in range(10):
        page.selecionar_cliente_externo("Ana Ferreira")
        page.val_input.setText(f"{i + 1},00")
        page._registrar_venda()

    ids = [v["id"] for v in page.historico_vendas]
    assert len(ids) == len(set(ids)), f"IDs duplicados gerados: {ids}"
