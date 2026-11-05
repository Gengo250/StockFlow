"""As premissas que os indicadores (US16) fazem sobre `fn_list_sales`.

O cálculo é testado sem banco; o que se prova AQUI é o contrato do qual ele
depende, contra PostgreSQL de verdade: que o status filtra, que o período
recorta e que uma venda com vários itens continua sendo uma linha só. Se
qualquer um dos três mudar no SQL, o faturamento fica errado sem nenhum
teste de domínio ficar vermelho.
"""

from uuid import uuid4

import pytest


@pytest.fixture
def caixa_aberto(db_tx, create_company):
    """Pré-condição dos snapshots de venda; não altera as fixtures globais."""
    db_tx.execute(
        "SELECT public.fn_start_my_register(%s, 0)",
        (create_company,),
    )


def _venda(db_tx, company, *, status, total, quando, itens=()):
    sale_id = uuid4()
    db_tx.execute("RESET ROLE")
    db_tx.execute(
        "INSERT INTO public.sales "
        "(id, company_id, client_id, client_name, total, status, created_on, created_by) "
        "VALUES (%s, %s, NULL, 'Cliente de teste', %s, %s::public.sale_status, %s, "
        "public.fn_current_user_id())",
        (sale_id, company, total, status, quando),
    )
    for nome, codigo, quantidade, preco in itens:
        db_tx.execute(
            "INSERT INTO public.sale_items "
            "(company_id, sale_id, product_name, product_code, quantity, unit_price) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (company, sale_id, nome, codigo, quantidade, preco),
        )
    db_tx.execute("SET LOCAL ROLE authenticated")
    return sale_id


def _confirmadas(db_tx, company, inicio=None, fim=None):
    return db_tx.execute(
        "SELECT total, total_count, items FROM public.fn_list_sales("
        "%s, p_from => %s, p_to => %s, p_status => 'CONCLUIDA', p_limit => 200)",
        (company, inicio, fim),
    ).fetchall()


def test_somente_vendas_concluidas_entram_no_faturamento(
    db_tx, create_company, caixa_aberto
):
    for status in ("CONCLUIDA", "CANCELADA", "DEVOLVIDA", "PENDENTE"):
        _venda(db_tx, create_company, status=status, total=10,
               quando="2026-05-10 12:00+00")

    linhas = _confirmadas(db_tx, create_company)

    assert [linha[0] for linha in linhas] == [10]


def test_o_periodo_recorta_pelo_instante_da_venda(
    db_tx, create_company, caixa_aberto
):
    """O limite superior é EXCLUSIVO: o adaptador manda o dia seguinte.

    É essa conversão que faz "até dia 10" incluir o dia 10 inteiro. Sem ela
    o último dia do período sumiria do faturamento.
    """
    _venda(db_tx, create_company, status="CONCLUIDA", total=10,
           quando="2026-05-09 23:00+00")
    _venda(db_tx, create_company, status="CONCLUIDA", total=20,
           quando="2026-05-10 23:00+00")
    _venda(db_tx, create_company, status="CONCLUIDA", total=40,
           quando="2026-05-11 01:00+00")

    linhas = _confirmadas(db_tx, create_company, "2026-05-10 00:00+00",
                          "2026-05-11 00:00+00")

    assert [linha[0] for linha in linhas] == [20]


def test_venda_com_varios_itens_continua_sendo_uma_linha(
    db_tx, create_company, caixa_aberto
):
    """Sem isso, a junção com `sale_items` multiplicaria a venda no total."""
    _venda(db_tx, create_company, status="CONCLUIDA", total=90,
           quando="2026-05-10 12:00+00",
           itens=(("Cabo HDMI", "PRD-1", 2, 10), ("Mouse", "PRD-2", 3, 20)))

    linhas = _confirmadas(db_tx, create_company)

    assert len(linhas) == 1
    assert linhas[0][1] == 1
    assert len(linhas[0][2]) == 2


def test_periodo_sem_vendas_devolve_nenhuma_linha(
    db_tx, create_company, caixa_aberto
):
    _venda(db_tx, create_company, status="CONCLUIDA", total=10,
           quando="2026-05-10 12:00+00")

    linhas = _confirmadas(db_tx, create_company, "2026-06-01 00:00+00",
                          "2026-07-01 00:00+00")

    assert linhas == []
