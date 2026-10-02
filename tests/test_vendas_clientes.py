"""Commit af9fb43 - feat(sales): provisional sales page + active customer link."""

import pytest


def itens_do_combo(page):
    return [page.cliente_combo.itemText(i) for i in range(page.cliente_combo.count())]


def linhas_do_historico(page):
    return [
        page.table.item(row, 0).text()
        for row in range(page.table.rowCount())
    ]


# ------------------------------------------------- combo de clientes

def test_combo_lista_apenas_clientes_ativos(vendas_page):
    textos = itens_do_combo(vendas_page)
    assert textos[0] == "Selecione um cliente..."
    assert any("Ana Ferreira" in t for t in textos)
    assert any("Carlos Mendes" in t for t in textos)
    assert any("Juliana Ramos" in t for t in textos)
    # Patrícia Lima está inativa
    assert not any("Patrícia Lima" in t for t in textos)


def test_placeholder_nao_carrega_cliente(vendas_page):
    assert vendas_page.cliente_combo.currentIndex() == 0
    assert vendas_page.cliente_combo.currentData() is None


def test_recarregar_nao_duplica_itens(vendas_page):
    antes = vendas_page.cliente_combo.count()
    vendas_page.recarregar_clientes_disponiveis()
    assert vendas_page.cliente_combo.count() == antes


# --------------------------------------- associação vinda da tela de clientes

def test_selecionar_cliente_ativo_externo(vendas_page):
    assert vendas_page.selecionar_cliente_externo("Carlos Mendes") is True
    assert vendas_page.cliente_combo.currentData()["nome"] == "Carlos Mendes"
    assert vendas_page.warning_label.text() == ""


def test_selecionar_cliente_inativo_e_recusado_com_aviso(vendas_page):
    assert vendas_page.selecionar_cliente_externo("Patrícia Lima") is False
    assert "inativo" in vendas_page.warning_label.text().lower()
    assert vendas_page.cliente_combo.currentData() is None


def test_cliente_desconhecido_recebe_mensagem_correta(vendas_page):
    """Um nome que não existe na base não é 'inativo' - é inexistente."""
    assert vendas_page.selecionar_cliente_externo("Roberto Souza") is False
    aviso = vendas_page.warning_label.text().lower()
    assert "inativo" not in aviso, f"mensagem enganosa: {vendas_page.warning_label.text()!r}"


# ------------------------------------------------------ registro de venda

def test_venda_sem_cliente_e_bloqueada(vendas_page):
    vendas_page.val_input.setText("100,00")
    vendas_page._registrar_venda()
    assert len(vendas_page.historico_vendas) == 2
    assert vendas_page.warning_label.text() == "Selecione um cliente ativo válido."


def test_venda_sem_valor_e_bloqueada(vendas_page):
    vendas_page.selecionar_cliente_externo("Ana Ferreira")
    vendas_page._registrar_venda()
    assert len(vendas_page.historico_vendas) == 2
    assert vendas_page.warning_label.text() == "Informe o valor da venda."


def test_venda_valida_entra_no_historico_com_o_cliente(vendas_page):
    vendas_page.selecionar_cliente_externo("Juliana Ramos")
    vendas_page.val_input.setText("250,00")
    vendas_page._registrar_venda()

    assert len(vendas_page.historico_vendas) == 3
    nova = vendas_page.historico_vendas[0]
    assert nova["cliente"] == "Juliana Ramos"
    assert nova["valor"] == "R$ 250,00"
    assert vendas_page.table.item(0, 1).text() == "Juliana Ramos"


def test_formulario_e_limpo_apos_a_venda(vendas_page):
    vendas_page.selecionar_cliente_externo("Ana Ferreira")
    vendas_page.val_input.setText("10,00")
    vendas_page._registrar_venda()
    assert vendas_page.val_input.text() == ""
    assert vendas_page.cliente_combo.currentIndex() == 0
    assert vendas_page.warning_label.text() == ""


def test_historico_preserva_cliente_inativo_de_venda_antiga(vendas_page):
    """Patrícia Lima está inativa, mas a venda antiga dela continua visível."""
    clientes = [vendas_page.table.item(r, 1).text() for r in range(vendas_page.table.rowCount())]
    assert "Patrícia Lima" in clientes


def test_ids_de_venda_nao_colidem(vendas_page):
    vendas_page.selecionar_cliente_externo("Ana Ferreira")
    for i in range(12):
        vendas_page.cliente_combo.setCurrentIndex(1)
        vendas_page.val_input.setText(f"{i + 1},00")
        vendas_page._registrar_venda()

    ids = [v["id"] for v in vendas_page.historico_vendas]
    assert len(ids) == len(set(ids)), f"IDs duplicados gerados: {sorted(ids)}"
