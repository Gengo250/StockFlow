"""Histórico de preço e custo da demonstração (H09).

Lê o rastro que `DemoProductRepository` grava, do mesmo jeito que
`fn_list_price_edits` lê a tabela que o trigger escreve. A semente existe
porque uma tela de histórico que só mostra o que você acabou de fazer não
demonstra histórico nenhum.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from stockflow.application.dto.audit_filter import AuditFilter, AuditPage
from stockflow.domain.enums.price_edit_field import PriceEditField
from stockflow.domain.price_change import PriceChange

#: `(dias atrás, código, campo, de, para, autor)`. Datas relativas a "agora"
#: para que a tela não envelheça sozinha — uma semente com datas fixas vira
#: "última alteração há oito meses" depois de um semestre parado.
#: Os códigos são de produtos que EXISTEM em `demo_products`. Semente que
#: aponta para produto inexistente é coerente com o banco (a auditoria
#: sobrevive ao seu alvo), mas na demonstração vira uma linha que o filtro
#: nunca oferece — parece defeito, não histórico.
SEMENTE = (
    (1, "PRD-009", PriceEditField.SELL_PRICE, "2599.90", "2499.90", "Ana Ferreira"),
    (3, "PRD-009", PriceEditField.BUY_PRICE, None, "1850.00", "Miguel Gengo"),
    (9, "PRD-007", PriceEditField.SELL_PRICE, "179.90", "189.90", "Ana Ferreira"),
)


class DemoPriceHistoryRepository:
    def __init__(self, products, seed=SEMENTE, agora=None):
        self._products = products
        self._agora = agora or datetime.now()
        self._semente = tuple(seed)

    def list_price_edits(self, product_code: str | None = None) -> tuple[PriceChange, ...]:
        linhas = self._da_semente() + self._do_rastro()

        if product_code is not None:
            linhas = [l for l in linhas if l[0].product_code == product_code]

        # Mesmo critério de `fn_list_price_edits`: mais recente primeiro, com
        # desempate estável. O que o desempate compra não é um "mais
        # recente" entre duas linhas do mesmo instante — entre elas não
        # existe ordem cronológica — e sim a garantia de que a tela não as
        # embaralhe entre um carregamento e o seguinte.
        linhas.sort(key=lambda par: (par[0].changed_on, par[1]), reverse=True)
        return tuple(linha for linha, _ in linhas)

    def list_audit_page(
        self,
        filtro: AuditFilter | None = None,
        page: int = 1,
        size: int = 50,
    ) -> AuditPage:
        filtro = filtro or AuditFilter()
        linhas = [par for par in (self._da_semente() + self._do_rastro()) if self._combina(par[0], filtro)]

        reverso = filtro.sort != "DATA_ASC"
        # Eventos sem data vão no final tanto na ordem crescente quanto decrescente
        linhas.sort(
            key=lambda par: (
                par[0].changed_on is not None,
                par[0].changed_on if par[0].changed_on else datetime.min,
                par[1],
            ),
            reverse=reverso,
        )

        total = len(linhas)
        inicio = (page - 1) * size
        selecionadas = tuple(par[0] for par in linhas[inicio : inicio + size])
        return AuditPage(rows=selecionadas, total=total, page=page, size=size)

    def _combina(self, mudanca: PriceChange, filtro: AuditFilter) -> bool:
        if filtro.product_code and mudanca.product_code != filtro.product_code:
            return False
        if filtro.user:
            usuario = (mudanca.changed_by or "").strip().lower()
            alvo = filtro.user.strip().lower()
            if alvo not in usuario:
                return False
        if filtro.action:
            campo = filtro.action.value if isinstance(filtro.action, PriceEditField) else str(filtro.action)
            if mudanca.field.value != campo and mudanca.field.name != campo:
                return False
        if filtro.entity:
            entidade = filtro.entity.strip().lower()
            if entidade not in ("produto", "produtos"):
                return False
        if filtro.date_from or filtro.date_to:
            if not mudanca.changed_on:
                return False
            data_evento = mudanca.changed_on.date() if isinstance(mudanca.changed_on, datetime) else mudanca.changed_on
            if filtro.date_from and data_evento < filtro.date_from:
                return False
            if filtro.date_to and data_evento > filtro.date_to:
                return False
        return True

    def _da_semente(self) -> list:
        linhas = []
        for posicao, (dias, codigo, campo, de, para, autor) in enumerate(self._semente):
            linhas.append((
                PriceChange(
                    changed_on=self._agora - timedelta(days=dias),
                    product_code=codigo,
                    product_name=self._nome(codigo),
                    field=campo,
                    old_price=None if de is None else Decimal(de),
                    new_price=None if para is None else Decimal(para),
                    changed_by=autor,
                ),
                # Negativo para que a semente nunca dispute o desempate com
                # uma edição real feita no mesmo instante: o que o usuário
                # acabou de fazer aparece primeiro.
                posicao - len(self._semente),
            ))
        return linhas

    def _do_rastro(self) -> list:
        return [
            (
                PriceChange(
                    changed_on=registro["changed_on"],
                    product_code=registro["product_code"],
                    product_name=self._nome(registro["product_code"]),
                    field=registro["field"],
                    old_price=registro["old_price"],
                    new_price=registro["new_price"],
                    changed_by=registro["changed_by"],
                ),
                registro["seq"],
            )
            for registro in getattr(self._products, "price_edits", ())
        ]

    def _nome(self, codigo: str) -> str:
        """Nome atual do produto, vazio quando ele não está mais no catálogo.

        Mesmo efeito do `LEFT JOIN` da consulta SQL: a linha de auditoria
        sobrevive ao seu alvo.
        """
        produto = self._products.get(codigo)
        return getattr(produto, "name", "") if produto is not None else ""
