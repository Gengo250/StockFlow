"""US04 — alertar produtos com estoque baixo.

Um teste por critério de conclusão do cartão:

    "A consulta inclui saldo igual ao mínimo, exclui inativos e produtos sem
     configuração e não retorna produtos acima do mínimo."

mais o que o cartão manda retornar: produto, saldo, mínimo e situação.

A regra é `domain/stock_level.py`, tradução literal de
`public.fn_stock_state`. Antes do alinhamento a UI tinha regra própria e
divergia do banco em 5 de 11 casos — inclusive tratando produto SEM mínimo
como se o mínimo fosse 10, o que violava diretamente o critério de exclusão
deste cartão.
"""

from stockflow.domain.stock_level import derive_stock_status
from stockflow.presentation.pages.estoque import MINIMUM, STATUS, STOCK

from test_estoque_busca_filtro import celula, clicar_filtro, visiveis

ALERTA = "Abaixo do mínimo"


def situacao(page, codigo):
    for produto in page.produtos:
        if produto[0] == codigo:
            return produto[STATUS]
    raise AssertionError(codigo)


# ======================================================= cálculo da situação


def test_situacao_sai_do_minimo_do_produto(estoque_page):
    assert situacao(estoque_page, "PRD-009") == "Normal"    # 18 contra 10
    assert situacao(estoque_page, "PRD-005") == "Atenção"   # 11 contra 10
    assert situacao(estoque_page, "PRD-008") == "Baixo"     #  6 contra 10
    assert situacao(estoque_page, "PRD-007") == "Baixo"     #  2 contra  5
    assert situacao(estoque_page, "PRD-006") == "Crítico"   #  0 contra 10
    assert situacao(estoque_page, "PRD-003") == "Normal"    #  3 sem mínimo
    assert situacao(estoque_page, "PRD-002") == "Crítico"   #  0 com mínimo 0


def test_situacao_acompanha_mudanca_de_saldo(estoque_page):
    produto = estoque_page.produtos[0]           # PRD-009, mínimo 10
    produto[STOCK] = "11"
    estoque_page.apply_filters()
    assert produto[STATUS] == "Atenção"

    produto[STOCK] = "9"
    estoque_page.apply_filters()
    assert produto[STATUS] == "Baixo"

    produto[STOCK] = "0"
    estoque_page.apply_filters()
    assert produto[STATUS] == "Crítico"


def test_situacao_ignora_o_valor_gravado_na_lista(estoque_page):
    """A situação é sempre derivada, nunca lida de volta.

    O valor da linha é cache. Confiar nele deixaria a coluna mentindo assim
    que o saldo mudasse por um caminho que esqueceu de reescrevê-la — e o
    filtro de alerta esconderia justamente o item que precisa aparecer.
    """
    produto = estoque_page.produtos[0]
    produto[STATUS] = "Crítico"                   # valor mentiroso
    estoque_page.apply_filters()
    assert produto[STATUS] == "Normal"


# ================================================ critérios de conclusão


def test_inclui_saldo_IGUAL_ao_minimo(estoque_page):
    """Primeiro critério. O limite é `<=`, não `<`."""
    produto = estoque_page.produtos[0]            # PRD-009, mínimo 10
    produto[STOCK] = "10"
    clicar_filtro(estoque_page, ALERTA)

    assert "PRD-009" in visiveis(estoque_page)
    assert situacao(estoque_page, "PRD-009") == "Baixo"


def test_exclui_inativos(estoque_page):
    """Segundo critério. Produto fora de operação não se repõe."""
    clicar_filtro(estoque_page, ALERTA)
    assert "PRD-008" in visiveis(estoque_page)

    estoque_page.toggle_product_status(estoque_page.produtos[1])   # PRD-008
    assert "PRD-008" not in visiveis(estoque_page)


def test_exclui_produtos_sem_minimo_configurado(estoque_page):
    """Terceiro critério, e o que a regra antiga da UI violava.

    PRD-003 tem saldo 3 e nenhum mínimo. Com o limiar implícito de 10 que a
    UI usava, ele aparecia como Crítico; sem limiar configurado, não há o que
    comparar e ele fica fora do alerta — que é o que `fn_stock_state` faz.
    """
    clicar_filtro(estoque_page, ALERTA)
    assert "PRD-003" not in visiveis(estoque_page)

    # Nem mesmo zerando o saldo ele entra: o que falta é a configuração.
    for produto in estoque_page.produtos:
        if produto[0] == "PRD-003":
            produto[STOCK] = "0"
    estoque_page.apply_filters()
    assert "PRD-003" not in visiveis(estoque_page)


def test_nao_retorna_produtos_acima_do_minimo(estoque_page):
    """Quarto critério. Inclusive os da faixa de atenção, que já estão acima."""
    clicar_filtro(estoque_page, ALERTA)
    mostrados = visiveis(estoque_page)

    assert "PRD-009" not in mostrados    # 18 contra 10, Normal
    assert "PRD-005" not in mostrados    # 11 contra 10, Atenção
    assert "PRD-003" not in mostrados    # saldo 3, mas SEM mínimo
    assert sorted(mostrados) == [
        "PRD-002", "PRD-006", "PRD-007", "PRD-008",
    ]


def test_retorna_produto_saldo_minimo_e_situacao(estoque_page):
    """O cartão pede os quatro; a tela precisa mostrar os quatro."""
    clicar_filtro(estoque_page, ALERTA)

    assert celula(estoque_page, "PRD-007", 1) == "Mouse ergonômico"
    assert celula(estoque_page, "PRD-007", STOCK) == "2"
    assert celula(estoque_page, "PRD-007", MINIMUM) == "5"
    assert celula(estoque_page, "PRD-007", STATUS) == "Baixo"


# ================================================ ordenação por criticidade


def test_alerta_ordena_do_mais_urgente_para_o_menos(estoque_page):
    """Pior situação primeiro e, dentro dela, menor saldo primeiro.

    Ordenar só por saldo misturaria um crítico de 0 com um "baixo" de 2 sem
    dizer qual é mais urgente.
    """
    clicar_filtro(estoque_page, ALERTA)
    # Críticos primeiro (PRD-006 e PRD-002, ambos zerados, em ordem de
    # cadastro), depois os baixos do menor saldo para o maior.
    assert visiveis(estoque_page) == [
        "PRD-006", "PRD-002", "PRD-007", "PRD-008",
    ]

    saldos = [
        int(estoque_page.table.item(row, STOCK).text())
        for row in range(estoque_page.table.rowCount())
    ]
    assert saldos == [0, 0, 2, 6]


def test_filtro_todos_mantem_a_ordem_de_cadastro(estoque_page):
    assert visiveis(estoque_page) == [
        "PRD-009", "PRD-008", "PRD-007", "PRD-006", "PRD-005", "PRD-003", "PRD-002",
    ]


# =========================================== a regra, sem passar pela tela


def test_regra_espelha_fn_stock_state():
    """Grade completa contra a tradução literal da função do banco.

    Se este teste e `public.fn_stock_state` discordarem, a tela mostra uma
    situação e um relatório SQL mostra outra.
    """
    casos = [
        # saldo, mínimo, situação esperada
        (0,  10, "Crítico"),   # sem unidade em mãos
        (1,  10, "Baixo"),     # só o zero é crítico
        (9,  10, "Baixo"),
        (10, 10, "Baixo"),     # IGUAL ao mínimo entra no alerta
        (11, 10, "Atenção"),   # 11 < 12
        (12, 10, "Normal"),    # 12 >= 10 × 1,2
        (30, 10, "Normal"),
        # O par que prova a US03: mesmo saldo zerado, respostas diferentes.
        (0,  None, "Normal"),   # ausente: nunca alerta, nem zerado
        (0,  0,    "Crítico"),                          # zero: avise ao acabar
        (5,  0,    "Normal"),   # mínimo zero só alerta quando o saldo acaba
        (1,  0,    "Normal"),
        (5,  None, "Normal"),
        (-3, 0,    "Crítico"),  # saldo negativo também
    ]
    for saldo, minimo, esperado in casos:
        assert derive_stock_status(saldo, minimo) == esperado, (saldo, minimo)
