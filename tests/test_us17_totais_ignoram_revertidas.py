"""Venda desfeita não é dinheiro vendido (US17).

A US17 não pediu isto, mas é ela que cria os estados CANCELADA e DEVOLVIDA:
sem esta exclusão, a própria história introduziria um número errado no
Dashboard e nos Relatórios.
"""

import pytest

from stockflow.presentation.pages.dashboard import DashboardPage
from stockflow.presentation.pages.reports import ReportsPage


class VendasFalsas:
    """Uma concluída de 100, uma cancelada de 50 e uma devolvida de 30."""

    def list_all(self):
        return [
            {"id": "1", "cliente": "Ana", "produto": "X", "valor": "R$ 100,00",
             "data": "01/10/2026", "total": "100.00", "status": "CONCLUIDA"},
            {"id": "2", "cliente": "Bia", "produto": "Y", "valor": "R$ 50,00",
             "data": "02/10/2026", "total": "50.00", "status": "CANCELADA"},
            {"id": "3", "cliente": "Cid", "produto": "Z", "valor": "R$ 30,00",
             "data": "03/10/2026", "total": "30.00", "status": "DEVOLVIDA"},
        ]


class CatalogoVazio:
    def list_all(self):
        return []

    def load_catalog(self):
        return {}


def test_dashboard_soma_so_o_que_continua_vendido(qapp):
    page = DashboardPage(CatalogoVazio(), VendasFalsas(), CatalogoVazio())
    page.read_products = lambda: []
    try:
        page.refresh()
        qapp.processEvents()
        receita = page.metric_values[2].text()
        assert "100,00" in receita, receita
        assert "180,00" not in receita
    finally:
        page.close()


def test_dashboard_continua_contando_todas_as_operacoes(qapp):
    """O histórico aconteceu: esconder a contagem seria outra mentira."""
    page = DashboardPage(CatalogoVazio(), VendasFalsas(), CatalogoVazio())
    page.read_products = lambda: []
    try:
        page.refresh()
        qapp.processEvents()
        assert "1 de 3 vendas" in page.metric_details[2].text()
    finally:
        page.close()


def test_relatorio_de_vendas_marca_as_revertidas(qapp):
    page = ReportsPage(CatalogoVazio(), VendasFalsas())
    try:
        page.kind.setCurrentIndex(1)
        page.refresh()
        qapp.processEvents()
        assert "Status" in page.headers
        assert page.table.rowCount() == 3
        situacoes = {
            page.table.item(linha, 5).text() for linha in range(page.table.rowCount())
        }
        assert situacoes == {"Concluída", "Cancelada", "Devolvida"}
    finally:
        page.close()


def test_relatorio_soma_so_o_que_continua_vendido(qapp):
    page = ReportsPage(CatalogoVazio(), VendasFalsas())
    try:
        page.kind.setCurrentIndex(1)
        page.refresh()
        qapp.processEvents()
        assert "100,00" in page.metrics[1][1].text()
        # Média sobre o que vale, não sobre as três linhas listadas.
        assert "100,00" in page.metrics[2][1].text()
    finally:
        page.close()
