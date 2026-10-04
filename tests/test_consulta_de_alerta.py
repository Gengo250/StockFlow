"""A regra que decide quem alerta pertence à CONSULTA, não à tela.

É o que o cartão da tela de alerta exige ao dizer "usar a consulta do
SCRUM-37" e "a regra que decide quais produtos geram alerta pertence à
consulta".

Por que isso não é formalidade: enquanto a tela decidia sozinha, havia duas
implementações do mesmo critério. A primeira vez que elas divergiram neste
projeto, a divergência passou despercebida e **violou um critério de
aceitação** — produto sem mínimo configurado aparecia no alerta.

O teste que prova a mudança é `test_a_consulta_ganha_da_regra_local`: ele dá
à tela um resultado que CONTRADIZ o cálculo local e verifica quem manda.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "unit"))

from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.infrastructure.repositories.supabase_product_repository import (
    SupabaseProductRepository,
)
from stockflow.presentation.demo_products import DEMO_PRODUCTS

from test_estoque_busca_filtro import clicar_filtro, visiveis
from test_supabase_product_repository import COMPANY, ClienteFalso, catalogo_falso

ALERTA = "Abaixo do mínimo"


# ================================================ a consulta é quem decide


def test_a_consulta_ganha_da_regra_local(estoque_page):
    """O teste que prova que a regra mudou de dono.

    O resultado abaixo contradiz o cálculo local de propósito: inclui um
    produto que a regra local considera Normal (PRD-009, saldo 18 contra
    mínimo 10) e omite dois que ela considera em alerta. Se a tela ainda
    decidisse, a lista sairia diferente.
    """
    estoque_page.set_alerts([("PRD-009", "18", 10, "Baixo")])
    clicar_filtro(estoque_page, ALERTA)

    assert visiveis(estoque_page) == ["PRD-009"]


def test_os_valores_exibidos_vem_da_consulta(estoque_page):
    """Alerta certo com número velho ao lado seria pior do que alerta nenhum."""
    estoque_page.set_alerts([("PRD-009", "3", 7, "Crítico")])
    clicar_filtro(estoque_page, ALERTA)

    linha = visiveis(estoque_page).index("PRD-009")
    assert estoque_page.table.item(linha, 3).text() == "3"     # saldo
    assert estoque_page.table.item(linha, 4).text() == "7"     # mínimo
    assert estoque_page.table.item(linha, 6).text() == "Crítico"


def test_consulta_vazia_esvazia_a_lista(estoque_page):
    """Zero em alerta é uma resposta, não ausência de resposta."""
    estoque_page.set_alerts([])
    clicar_filtro(estoque_page, ALERTA)

    assert visiveis(estoque_page) == []
    assert estoque_page.list_state_label.isVisibleTo(estoque_page)
    assert "alerta" in estoque_page.list_state_label.text().casefold()


def test_sem_consulta_ligada_a_regra_local_responde(estoque_page):
    """Página isolada, sem janela: não há repositório a consultar.

    O cálculo local é o espelho declarado de `fn_stock_state`, com teste de
    grade comparando os dois caso a caso — não é uma segunda regra, é a
    mesma traduzida.
    """
    assert estoque_page._alertas is None
    clicar_filtro(estoque_page, ALERTA)

    assert sorted(visiveis(estoque_page)) == [
        "PRD-002", "PRD-006", "PRD-007", "PRD-008",
    ]


def test_a_busca_ainda_filtra_dentro_do_alerta(estoque_page):
    estoque_page.set_alerts([
        ("PRD-008", "6", 10, "Baixo"), ("PRD-007", "2", 5, "Baixo"),
    ])
    clicar_filtro(estoque_page, ALERTA)
    estoque_page.search_input.setText("mouse")

    assert visiveis(estoque_page) == ["PRD-007"]


# ============================================== os dois adaptadores da porta


def test_o_adaptador_de_banco_le_a_view():
    """A view já aplica os critérios; refiltrar aqui recriaria a duplicação."""
    tabelas = catalogo_falso()
    tabelas["vw_stock_alerts"] = [
        {"company_id": COMPANY, "product_code": "PRD-009",
         "current_balance": 4, "min_quantity": 10, "state": "BAIXO"},
    ]
    cliente = ClienteFalso(tabelas)

    alertas = SupabaseProductRepository(cliente, COMPANY).list_alerts()

    assert alertas == (("PRD-009", "4", 10, "Baixo"),)
    consultadas = [t for t, _ in cliente.consultas]
    assert "vw_stock_alerts" in consultadas


def test_o_adaptador_de_banco_escopa_por_empresa():
    tabelas = catalogo_falso()
    tabelas["vw_stock_alerts"] = []
    cliente = ClienteFalso(tabelas)

    SupabaseProductRepository(cliente, COMPANY).list_alerts()

    filtros = [f for t, f in cliente.consultas if t == "vw_stock_alerts"]
    assert filtros and all(f.get("company_id") == COMPANY for f in filtros)


def test_o_adaptador_de_banco_traduz_a_situacao():
    """`public.stock_state` é caixa alta e sem acento; a tela lê rótulo."""
    tabelas = catalogo_falso()
    tabelas["vw_stock_alerts"] = [
        {"company_id": COMPANY, "product_code": "A", "current_balance": 0,
         "min_quantity": 5, "state": "CRITICO"},
    ]
    assert SupabaseProductRepository(ClienteFalso(tabelas), COMPANY).list_alerts()[0][3] \
        == "Crítico"


def test_o_adaptador_de_demonstracao_aplica_os_mesmos_criterios():
    """Sem banco não há view, mas o critério continua num lugar só."""
    alertas = DemoProductRepository(dict(DEMO_PRODUCTS)).list_alerts()
    codigos = {linha[0] for linha in alertas}

    assert codigos == {"PRD-008", "PRD-007", "PRD-006", "PRD-002"}
    assert "PRD-003" not in codigos     # sem mínimo configurado
    assert "PRD-009" not in codigos     # acima do mínimo
    assert "PRD-005" not in codigos     # acima do mínimo (Atenção)


def test_o_adaptador_de_demonstracao_exclui_inativos():
    import dataclasses

    catalogo = dict(DEMO_PRODUCTS)
    catalogo["PRD-006"] = dataclasses.replace(catalogo["PRD-006"], active=False)

    codigos = {l[0] for l in DemoProductRepository(catalogo).list_alerts()}
    assert "PRD-006" not in codigos


@pytest.mark.parametrize("adaptador", ["demo", "supabase"])
def test_a_porta_exige_list_alerts_dos_dois(adaptador):
    classe = {"demo": DemoProductRepository,
              "supabase": SupabaseProductRepository}[adaptador]
    assert hasattr(classe, "list_alerts")
