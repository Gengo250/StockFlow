"""US04: alerta de estoque baixo e ordenação por criticidade (commit 9357b66)."""

import pytest

from stockflow.presentation.pages.estoque import EstoquePage


@pytest.fixture
def page(qapp):
    return EstoquePage()


def set_filter(page, label):
    button = next(b for b in page.filter_buttons if b.text() == label)
    page.select_filter(button)


def visible_codes(page):
    return [page.table.item(r, 0).text() for r in range(page.table.rowCount())]


def status_of(page, codigo):
    return next(p[5] for p in page.produtos if p[0] == codigo)


@pytest.mark.parametrize(
    "estoque,minimo,esperado",
    [
        (0, 10, "Crítico"),    # zerado
        (5, 10, "Crítico"),    # <= metade do mínimo
        (6, 10, "Baixo"),      # acima da metade, <= mínimo
        (10, 10, "Baixo"),     # exatamente no mínimo
        (11, 10, "Normal"),    # acima do mínimo
        (2, 5, "Crítico"),     # 5//2 = 2
        (3, 5, "Baixo"),
        (1, 0, "Crítico"),     # max(1, 0) = 1
        (2, 0, "Normal"),
    ],
)
def test_classificacao_de_status_por_estoque_minimo(page, estoque, minimo, esperado):
    page.produtos = [["PRD-X", "Teste", "Cat", str(estoque), "R$ 1,00", "", True, minimo]]
    page.apply_filters()
    assert page.produtos[0][5] == esperado


def test_status_e_recalculado_e_nao_confia_no_valor_gravado(page):
    # Valor gravado é intencionalmente errado; apply_filters deve corrigir.
    page.produtos[0][5] = "Crítico"
    page.apply_filters()
    assert status_of(page, "PRD-009") == "Normal"


def test_filtro_critico_lista_apenas_criticos(page):
    set_filter(page, "Crítico")
    assert sorted(visible_codes(page)) == ["PRD-006", "PRD-007"]


def test_filtro_baixo_lista_apenas_baixos(page):
    set_filter(page, "Baixo")
    assert visible_codes(page) == ["PRD-008"]


def test_ordenacao_por_criticidade_no_filtro_critico(page):
    set_filter(page, "Crítico")
    estoques = [int(page.table.item(r, 3).text()) for r in range(page.table.rowCount())]
    assert estoques == sorted(estoques), "Críticos devem vir do menor para o maior estoque"
    assert visible_codes(page) == ["PRD-006", "PRD-007"]


def test_sem_ordenacao_forcada_no_filtro_todos(page):
    set_filter(page, "Todos")
    assert visible_codes(page) == ["PRD-009", "PRD-008", "PRD-007", "PRD-006"]


def test_produto_inativo_nao_aparece_em_alertas(page):
    critico = next(p for p in page.produtos if p[0] == "PRD-006")
    page.toggle_product_status(critico)
    set_filter(page, "Crítico")
    assert visible_codes(page) == ["PRD-007"]
