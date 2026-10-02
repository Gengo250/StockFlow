"""US: busca e filtro no catálogo + toggle de status (commit 4fab981)."""

import pytest

from stockflow.presentation.pages.estoque import EstoquePage


@pytest.fixture
def page(qapp):
    return EstoquePage()


def visible_codes(page):
    return [
        page.table.item(row, 0).text()
        for row in range(page.table.rowCount())
    ]


def visible_status(page):
    return [
        page.table.item(row, 5).text()
        for row in range(page.table.rowCount())
    ]


def set_filter(page, label):
    button = next(b for b in page.filter_buttons if b.text() == label)
    page.select_filter(button)


def test_estado_inicial_mostra_todos_os_ativos(page):
    assert visible_codes(page) == ["PRD-009", "PRD-008", "PRD-007", "PRD-006"]
    assert page.subtitle.text() == "4 produtos cadastrados"


def test_busca_por_nome_e_case_insensitive(page):
    page.search_input.setText("MONITOR")
    assert visible_codes(page) == ["PRD-009"]


def test_busca_por_codigo(page):
    page.search_input.setText("prd-007")
    assert visible_codes(page) == ["PRD-007"]


def test_busca_por_categoria(page):
    page.search_input.setText("perifericos")
    assert visible_codes(page) == []  # sem acento não casa

    page.search_input.setText("Periféricos")
    assert sorted(visible_codes(page)) == ["PRD-007", "PRD-008"]


def test_busca_sem_resultado_limpa_tabela(page):
    page.search_input.setText("inexistente-xyz")
    assert page.table.rowCount() == 0
    assert page.subtitle.text() == "0 produtos cadastrados"


def test_busca_e_filtro_sao_combinados(page):
    page.search_input.setText("Periféricos")
    set_filter(page, "Crítico")
    assert visible_codes(page) == ["PRD-007"]


def test_filtro_normal(page):
    set_filter(page, "Normal")
    assert visible_codes(page) == ["PRD-009"]


def test_filtro_inativos_vazio_por_padrao(page):
    set_filter(page, "Inativos")
    assert visible_codes(page) == []


def test_toggle_move_produto_para_inativos(page):
    produto = page.produtos[0]  # PRD-009
    page.toggle_product_status(produto)

    assert produto[6] is False
    assert "PRD-009" not in visible_codes(page)

    set_filter(page, "Inativos")
    assert visible_codes(page) == ["PRD-009"]
    assert visible_status(page) == ["Inativo"]


def test_toggle_e_reversivel(page):
    produto = page.produtos[0]
    page.toggle_product_status(produto)
    page.toggle_product_status(produto)

    assert produto[6] is True
    assert "PRD-009" in visible_codes(page)


def test_apenas_um_filtro_fica_selecionado(page):
    set_filter(page, "Baixo")
    marcados = [b.text() for b in page.filter_buttons if b.isChecked()]
    assert marcados == ["Baixo"]
