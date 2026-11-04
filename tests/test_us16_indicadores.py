"""Indicadores de vendas e estoque por período (US16).

Os cálculos vivem no domínio e são PUROS: recebem as linhas que o
repositório já devolve e não falam com banco nenhum. É isso que permite
cobrir período vazio, venda cancelada e precisão monetária sem subir
infraestrutura — e é no serviço, não aqui, que a permissão é conferida.
"""

from decimal import Decimal

import pytest

from stockflow.domain.sales_indicators import (
    low_stock_products,
    summarize_sales,
)
from stockflow.presentation.demo_products import Product


def venda(total, itens=(), status="CONCLUIDA"):
    """Linha do histórico no formato que `fn_list_sales` e o Demo produzem."""
    return {
        "id": f"VND-{total}",
        "total": str(total),
        "status": status,
        "items": [
            {"product_code": code, "product_name": name, "quantity": quantidade}
            for code, name, quantidade in itens
        ],
    }


def produto(code, name, stock, minimum, active=True):
    return Product(
        code=code, name=name, category="Geral", unit="Unidade (UN)",
        sale_price="R$ 10,00", cost="R$ 5,00", active=active, stock=str(stock),
        stock_status="", minimum_stock=minimum,
    )


# ------------------------------------------------------------- faturamento


def test_faturamento_soma_os_totais_das_vendas():
    resumo = summarize_sales([venda("100.00"), venda("50.50")])

    assert resumo.revenue == Decimal("150.50")


def test_faturamento_usa_o_total_gravado_e_nao_a_soma_dos_itens():
    """O total já vem líquido de desconto; refazê-lo pelos itens inflaria.

    Reconstruir o valor histórico com preço de catálogo é exatamente o que
    a US16 proíbe: a venda abaixo tem 100,00 em itens e 90,00 gravados.
    """
    linha = venda("90.00", itens=(("PRD-1", "Cabo HDMI", 10),))

    assert summarize_sales([linha]).revenue == Decimal("90.00")


def test_faturamento_de_periodo_sem_vendas_e_zero():
    assert summarize_sales([]).revenue == Decimal("0.00")


# -------------------------------------------------------- quantidade/ticket


def test_quantidade_conta_vendas_e_nao_itens():
    """Venda com três itens continua sendo UMA venda."""
    linha = venda("300.00", itens=(
        ("PRD-1", "Cabo", 1), ("PRD-2", "Mouse", 2), ("PRD-3", "Teclado", 3),
    ))

    assert summarize_sales([linha]).sales_count == 1


def test_ticket_medio_e_o_faturamento_dividido_pelas_vendas():
    resumo = summarize_sales([venda("100.00"), venda("40.00")])

    assert resumo.average_ticket == Decimal("70.00")


def test_ticket_medio_sem_vendas_e_zero_e_nao_divisao_por_zero():
    resumo = summarize_sales([])

    assert resumo.sales_count == 0
    assert resumo.average_ticket == Decimal("0.00")


def test_ticket_medio_arredonda_para_o_centavo():
    """100,00 em três vendas dá 33,3333…; o indicador mostra centavos."""
    resumo = summarize_sales([venda("40.00"), venda("30.00"), venda("30.00")])

    assert resumo.average_ticket == Decimal("33.33")


def test_valores_sao_decimais_e_nunca_float():
    """`float` traz 0,01 de erro na soma de uma venda — a coluna é numeric."""
    resumo = summarize_sales([venda("0.10"), venda("0.20")])

    assert resumo.revenue == Decimal("0.30")
    assert isinstance(resumo.revenue, Decimal)
    assert isinstance(resumo.average_ticket, Decimal)


# ------------------------------------------------------------------ ranking


def test_ranking_soma_a_quantidade_do_mesmo_produto_em_vendas_diferentes():
    linhas = [
        venda("10.00", itens=(("PRD-1", "Cabo HDMI", 2),)),
        venda("20.00", itens=(("PRD-1", "Cabo HDMI", 3),)),
    ]

    ranking = summarize_sales(linhas).ranking

    assert [(i.code, i.name, i.quantity) for i in ranking] == [("PRD-1", "Cabo HDMI", 5)]


def test_ranking_ordena_da_maior_para_a_menor_quantidade():
    linha = venda("90.00", itens=(
        ("PRD-1", "Cabo", 1), ("PRD-2", "Mouse", 7), ("PRD-3", "Teclado", 4),
    ))

    vendidos = [item.code for item in summarize_sales([linha]).ranking]

    assert vendidos == ["PRD-2", "PRD-3", "PRD-1"]


def test_ranking_desempata_pelo_nome_do_produto():
    """Sem desempate, duas quantidades iguais trocam de lugar entre consultas."""
    linha = venda("20.00", itens=(("PRD-2", "Zebra", 2), ("PRD-1", "Abacaxi", 2)))

    nomes = [item.name for item in summarize_sales([linha]).ranking]

    assert nomes == ["Abacaxi", "Zebra"]


def test_venda_sem_itens_nao_quebra_o_ranking():
    """Venda antiga pode não ter snapshot de item; isso não é erro de tela."""
    resumo = summarize_sales([venda("10.00")])

    assert resumo.ranking == ()
    assert resumo.revenue == Decimal("10.00")


# ------------------------------------------------------------ estoque baixo


def test_estoque_baixo_lista_produto_com_saldo_abaixo_do_minimo():
    baixos = low_stock_products([produto("PRD-1", "Cabo", stock=2, minimum=10)])

    assert [(p.code, p.stock, p.minimum) for p in baixos] == [("PRD-1", 2, 10)]


def test_estoque_baixo_inclui_saldo_igual_ao_minimo():
    """Mesma regra da US04 (`vw_stock_alerts`): o `<=` é deliberado."""
    baixos = low_stock_products([produto("PRD-1", "Cabo", stock=10, minimum=10)])

    assert [p.code for p in baixos] == ["PRD-1"]


def test_estoque_baixo_ignora_produto_acima_do_minimo():
    assert low_stock_products([produto("PRD-1", "Cabo", stock=50, minimum=10)]) == ()


def test_estoque_baixo_ignora_produto_sem_minimo_configurado():
    """Sem limiar não há o que comparar — inventar um alertaria por nada."""
    assert low_stock_products([produto("PRD-1", "Cabo", 0, minimum=None)]) == ()


def test_estoque_baixo_ignora_produto_inativo():
    inativo = produto("PRD-1", "Cabo", stock=0, minimum=10, active=False)

    assert low_stock_products([inativo]) == ()


def test_estoque_baixo_ordena_o_critico_antes_do_baixo():
    produtos = [
        produto("PRD-1", "Baixo", stock=9, minimum=10),
        produto("PRD-2", "Critico", stock=0, minimum=10),
    ]

    assert [p.code for p in low_stock_products(produtos)] == ["PRD-2", "PRD-1"]


def test_estoque_baixo_informa_a_situacao_do_produto():
    baixos = low_stock_products([produto("PRD-1", "Cabo", stock=0, minimum=10)])

    assert baixos[0].status == "Crítico"
