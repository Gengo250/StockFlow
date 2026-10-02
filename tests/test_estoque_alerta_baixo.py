"""Commit 9357b66 - feat(inventory): low stock alert + sorting by criticality (US04)."""

from test_estoque_busca_filtro import clicar_filtro, visiveis


def status_calculado(page, codigo):
    for produto in page.produtos:
        if produto[0] == codigo:
            return produto[5]
    raise AssertionError(codigo)


# ------------------------------------------------- cálculo do status

def test_status_e_recalculado_a_partir_do_estoque_minimo(estoque_page):
    # estoque 18, mínimo 10  -> Normal
    assert status_calculado(estoque_page, "PRD-009") == "Normal"
    # estoque 6,  mínimo 10  -> Baixo
    assert status_calculado(estoque_page, "PRD-008") == "Baixo"
    # estoque 2,  mínimo 5   -> Crítico (<= metade do mínimo)
    assert status_calculado(estoque_page, "PRD-007") == "Crítico"
    # estoque 0,  mínimo 10  -> Crítico
    assert status_calculado(estoque_page, "PRD-006") == "Crítico"


def test_status_acompanha_mudanca_de_estoque(estoque_page):
    produto = estoque_page.produtos[0]           # PRD-009, mínimo 10
    produto[3] = "9"
    estoque_page.apply_filters()
    assert produto[5] == "Baixo"

    produto[3] = "3"
    estoque_page.apply_filters()
    assert produto[5] == "Crítico"

    produto[3] = "40"
    estoque_page.apply_filters()
    assert produto[5] == "Normal"


def test_status_ignora_o_valor_gravado_na_lista(estoque_page):
    """O status da lista é sobrescrito pelo cálculo, nunca confiado."""
    produto = estoque_page.produtos[0]
    produto[5] = "Crítico"                        # valor mentiroso
    estoque_page.apply_filters()
    assert produto[5] == "Normal"


def test_estoque_zero_e_sempre_critico(estoque_page):
    for produto in estoque_page.produtos:
        produto[3] = "0"
    estoque_page.apply_filters()
    assert all(p[5] == "Crítico" for p in estoque_page.produtos)


# --------------------------------------------- ordenação por criticidade

def test_filtro_critico_ordena_do_menor_estoque_para_o_maior(estoque_page):
    clicar_filtro(estoque_page, "Crítico")
    # PRD-006 tem 0 e PRD-007 tem 2 -> o mais crítico vem primeiro
    assert visiveis(estoque_page) == ["PRD-006", "PRD-007"]


def test_filtro_baixo_tambem_ordena_por_estoque(estoque_page):
    estoque_page.produtos.append(
        ["PRD-010", "Suporte de monitor", "Acessórios", "9", "R$ 120,00", "Baixo", True, 12]
    )
    clicar_filtro(estoque_page, "Baixo")
    estoques = [
        int(estoque_page.table.item(row, 3).text())
        for row in range(estoque_page.table.rowCount())
    ]
    assert estoques == sorted(estoques)


def test_filtro_todos_mantem_a_ordem_de_cadastro(estoque_page):
    assert visiveis(estoque_page) == ["PRD-009", "PRD-008", "PRD-007", "PRD-006"]
