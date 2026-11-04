"""Consulta dos indicadores: recorte, paginação e alçada (US16).

A camada de domínio prova o CÁLCULO; este arquivo prova o que chega até
ela. São duas perguntas diferentes e uma só não cobre a outra: um resumo
perfeito sobre o conjunto errado de vendas continua sendo número errado.
"""

from datetime import date
from decimal import Decimal

import pytest

from stockflow.application.dto.sale_filter import SaleFilter, SalePage, TAMANHO_MAXIMO
from stockflow.domain.entities.session import Session
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.application.services.indicators_service import IndicatorsService


def sessao(papel):
    return Session("u-1", "Usuário", "u@example.com", papel, company_id="c-1")


ADMIN = sessao(UserRole.ADMIN)


def linha(sale_id, total, itens=()):
    return {
        "id": sale_id,
        "total": str(total),
        "status": "CONCLUIDA",
        "items": [
            {"product_code": c, "product_name": n, "quantity": q} for c, n, q in itens
        ],
    }


class VendasFalsas:
    """Dublê de `SaleService` que pagina como `fn_list_sales` pagina.

    Fatia uma lista única pelo `size` recebido, em vez de devolver páginas
    pré-montadas: um dublê que ignora o `size` deixaria a paginação do
    serviço passar sem ser exercitada, e o teste ficaria verde sobre nada.
    """

    def __init__(self, linhas=()):
        self.linhas = list(linhas)
        self.chamadas = []

    def list_sales(self, session, filtro, page, size):
        self.chamadas.append((session, filtro, page, size))
        inicio = (page - 1) * size
        return SalePage(rows=tuple(self.linhas[inicio:inicio + size]),
                        total=len(self.linhas), page=page, size=size)


class VendasProibidas:
    """Qualquer leitura aqui é uma consulta que não deveria ter acontecido."""

    def list_sales(self, *args, **kwargs):
        raise AssertionError("consulta executada antes da verificação de permissão")


class CatalogoFalso:
    def __init__(self, produtos=()):
        self.produtos = tuple(produtos)

    def list_all(self):
        return self.produtos


class CatalogoProibido:
    def list_all(self):
        raise AssertionError("catálogo lido antes da verificação de permissão")


def servico(vendas=None, catalogo=None):
    return IndicatorsService(vendas or VendasFalsas(), catalogo or CatalogoFalso())


# ------------------------------------------------------------------ recorte


def test_consulta_pede_apenas_vendas_concluidas():
    """CANCELADA, DEVOLVIDA e PENDENTE ficam fora pelo FILTRO, no banco.

    Trazer tudo e descartar depois gastaria a consulta e deixaria a regra
    comercial dependendo de um `if` na aplicação.
    """
    vendas = VendasFalsas()

    servico(vendas).commercial(ADMIN, date(2026, 1, 1), date(2026, 1, 31))

    _, filtro, _, _ = vendas.chamadas[0]
    assert filtro.status == "CONCLUIDA"


def test_consulta_leva_o_periodo_escolhido_para_o_filtro():
    vendas = VendasFalsas()

    servico(vendas).commercial(ADMIN, date(2026, 3, 1), date(2026, 3, 31))

    _, filtro, _, _ = vendas.chamadas[0]
    assert (filtro.date_from, filtro.date_to) == (date(2026, 3, 1), date(2026, 3, 31))


def test_periodo_invertido_e_recusado_antes_da_consulta():
    vendas = VendasFalsas()

    with pytest.raises(ValueError):
        servico(vendas).commercial(ADMIN, date(2026, 3, 31), date(2026, 3, 1))

    assert vendas.chamadas == []


def test_sem_periodo_a_consulta_cobre_todo_o_historico():
    vendas = VendasFalsas()

    servico(vendas).commercial(ADMIN)

    _, filtro, _, _ = vendas.chamadas[0]
    assert (filtro.date_from, filtro.date_to) == (None, None)


def test_consulta_percorre_todas_as_paginas():
    """O teto de `fn_list_sales` é 200 linhas por chamada.

    Período com mais vendas que isso não pode perder as excedentes: parar na
    primeira página daria faturamento menor que o real justamente nos meses
    movimentados, que são os que alguém consulta.
    """
    vendas = VendasFalsas([linha(str(i), "1.00") for i in range(TAMANHO_MAXIMO + 50)])

    resumo = servico(vendas).commercial(ADMIN)

    assert resumo.sales_count == TAMANHO_MAXIMO + 50
    assert resumo.revenue == Decimal(TAMANHO_MAXIMO + 50).quantize(Decimal("0.01"))
    assert [chamada[2] for chamada in vendas.chamadas] == [1, 2]


def test_consulta_usa_a_pagina_cheia_para_nao_multiplicar_idas_ao_banco():
    vendas = VendasFalsas()

    servico(vendas).commercial(ADMIN)

    assert vendas.chamadas[0][3] == TAMANHO_MAXIMO


def test_periodo_sem_vendas_devolve_indicadores_zerados():
    resumo = servico(VendasFalsas()).commercial(ADMIN)

    assert resumo.revenue == Decimal("0.00")
    assert resumo.sales_count == 0
    assert resumo.average_ticket == Decimal("0.00")
    assert resumo.ranking == ()


def test_venda_com_varios_itens_pesa_uma_vez_na_quantidade():
    vendas = VendasFalsas([
        linha("1", "90.00", itens=(("A", "Cabo", 1), ("B", "Mouse", 2))),
    ])

    resumo = servico(vendas).commercial(ADMIN)

    assert resumo.sales_count == 1
    assert resumo.revenue == Decimal("90.00")


# -------------------------------------------------------------- estoque


def test_estoque_baixo_le_o_catalogo_atual():
    from stockflow.presentation.demo_products import Product

    produto = Product("PRD-1", "Cabo", "Geral", "Unidade (UN)", "R$ 10,00",
                      "R$ 5,00", True, "1", "", minimum_stock=10)

    baixos = servico(catalogo=CatalogoFalso([produto])).low_stock(ADMIN)

    assert [p.code for p in baixos] == ["PRD-1"]


# -------------------------------------------------------------- permissão


@pytest.mark.parametrize("papel", [UserRole.STOCK, UserRole.SELLER])
def test_perfil_sem_alcada_nao_consulta_indicadores(papel):
    with pytest.raises(PermissionDeniedError):
        servico(VendasProibidas()).commercial(sessao(papel))


@pytest.mark.parametrize("papel", [UserRole.STOCK, UserRole.SELLER])
def test_perfil_sem_alcada_nao_consulta_estoque_baixo(papel):
    with pytest.raises(PermissionDeniedError):
        servico(catalogo=CatalogoProibido()).low_stock(sessao(papel))


def test_sessao_ausente_e_recusada():
    """Falha fechada: sem login, nega — como no resto da matriz."""
    with pytest.raises(PermissionDeniedError):
        servico(VendasProibidas()).commercial(None)


def test_administrador_consulta():
    resumo = servico(VendasFalsas([linha("1", "25.00")])).commercial(ADMIN)

    assert resumo.revenue == Decimal("25.00")


def test_a_recusa_acontece_antes_de_qualquer_consulta():
    """Esconder o menu é controle visual, e controle visual se burla.

    `VendasProibidas` levanta `AssertionError` se for tocado; o teste só
    passa se a recusa vier da permissão, não de uma consulta vazia.
    """
    with pytest.raises(PermissionDeniedError):
        servico(VendasProibidas(), CatalogoProibido()).commercial(
            sessao(UserRole.SELLER)
        )
