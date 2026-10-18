"""Consulta cronológica do histórico de preço e custo (H09).

Do adaptador de banco o que se prova aqui é o CONTRATO: qual função ele
chama, com quais argumentos e como traduz a linha. Do adaptador de
demonstração se prova mais, porque ele É a implementação inteira — sem
trigger, quem registra a mudança é ele, e sem isso a tela abre vazia no modo
em que o app abre por padrão.

A ordem é o ponto delicado da história, e não a listagem: preço e custo
alterados no mesmo salvamento acontecem no MESMO instante. Entre eles não
existe "mais recente" — existe apenas a obrigação de não embaralhar entre uma
consulta e outra.
"""

import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stockflow.application.services.price_history_service import PriceHistoryService
from stockflow.domain.entities.session import Session
from stockflow.domain.enums.price_edit_field import PriceEditField
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.price_change import PriceChange
from stockflow.infrastructure.repositories.demo_price_history_repository import (
    DemoPriceHistoryRepository,
)
from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.infrastructure.repositories.supabase_price_history_repository import (
    SupabasePriceHistoryRepository,
)
from stockflow.infrastructure.repositories.supabase_product_repository import (
    SupabaseProductRepository,
)

from test_supabase_product_repository import COMPANY, PRODUTO_ID, ClienteFalso, catalogo_falso

AGORA = datetime(2026, 10, 15, 14, 30)


def sessao(papel):
    return Session("u-1", "Quem olha", "olha@local.invalid", papel, COMPANY)


class RepositorioFalso:
    def __init__(self, linhas=()):
        self.linhas = tuple(linhas)
        self.filtros = []

    def list_price_edits(self, product_code=None):
        self.filtros.append(product_code)
        return self.linhas


def mudanca(**kwargs):
    base = dict(
        changed_on=AGORA,
        product_code="PRD-004",
        product_name="Cabo HDMI 2m",
        field=PriceEditField.SELL_PRICE,
        old_price=Decimal("20.00"),
        new_price=Decimal("25.00"),
        changed_by="Miguel",
    )
    base.update(kwargs)
    return PriceChange(**base)


# ------------------------------------------------------------------ o campo


def test_o_campo_auditado_espelha_o_enum_do_banco():
    """Enum da aplicação que inventa valor vira recusa de TIPO no Postgres."""
    sql = (RAIZ / "database/code/tables/09_price_edit_log.sql").read_text(encoding="utf-8")
    declarado = re.search(
        r"CREATE TYPE\s+public\.price_edit_field\s+AS ENUM\s*\((.*?)\)", sql, re.S
    )
    assert declarado, "tipo price_edit_field não declarado"

    assert {v.value for v in PriceEditField} == set(
        re.findall(r"'(\w+)'", declarado.group(1))
    )


def test_o_campo_tem_rotulo_que_cabe_na_coluna():
    assert PriceEditField.SELL_PRICE.label == "Venda"
    assert PriceEditField.BUY_PRICE.label == "Custo"


# --------------------------------------------------------------- permissão


@pytest.mark.parametrize("papel", [UserRole.SELLER, UserRole.STOCK])
def test_quem_nao_e_admin_nao_consulta_o_historico(papel):
    """A policy `price_edit_log_select` já decide isso no banco.

    A aplicação recusa antes para dar a mensagem em português, mas a decisão
    é a mesma — divergir aqui seria a tela prometer uma consulta que o banco
    devolveria vazia.
    """
    servico = PriceHistoryService(RepositorioFalso([mudanca()]))

    with pytest.raises(PermissionDeniedError):
        servico.list_changes(sessao(papel))


def test_o_admin_recebe_as_mudancas():
    repositorio = RepositorioFalso([mudanca()])
    servico = PriceHistoryService(repositorio)

    assert servico.list_changes(sessao(UserRole.ADMIN)) == repositorio.linhas


def test_a_recusa_acontece_antes_de_tocar_o_repositorio():
    """Sem isto, o papel barrado ainda gastaria a consulta que ele não pode ler."""
    repositorio = RepositorioFalso([mudanca()])

    with pytest.raises(PermissionDeniedError):
        PriceHistoryService(repositorio).list_changes(sessao(UserRole.SELLER))

    assert repositorio.filtros == []


def test_o_filtro_de_produto_chega_ao_repositorio():
    repositorio = RepositorioFalso()
    PriceHistoryService(repositorio).list_changes(sessao(UserRole.ADMIN), "PRD-004")

    assert repositorio.filtros == ["PRD-004"]


# ----------------------------------------------------------- demonstração


def produtos_demo():
    from stockflow.presentation.demo_products import Product

    return {
        "PRD-004": Product(
            code="PRD-004", name="Cabo HDMI 2m", category="Acessórios", unit="UN",
            sale_price="R$ 20,00", cost="R$ 8,00", stock="10", active=True,
            stock_status="NORMAL",
        )
    }


def repositorios_demo():
    produtos = DemoProductRepository(produtos_demo())
    return produtos, DemoPriceHistoryRepository(produtos, seed=())


def editar(produtos, **mudancas):
    from stockflow.application.dto.product_input import ProductInput

    atual = produtos.get("PRD-004")
    campos = dict(
        code=atual.code, name=atual.name, category=atual.category, unit=atual.unit,
        sale_price=atual.sale_price, cost=atual.cost, stock=atual.stock,
        active=atual.active,
    )
    campos.update(mudancas)
    produtos.update("PRD-004", ProductInput(**campos))


def test_a_demonstracao_registra_a_mudanca_de_preco():
    """Sem trigger, quem registra é o adaptador — ou a tela abre vazia."""
    produtos, historico = repositorios_demo()
    editar(produtos, sale_price="R$ 25,00")

    linhas = historico.list_price_edits()

    assert len(linhas) == 1
    assert linhas[0].field is PriceEditField.SELL_PRICE
    assert linhas[0].old_price == Decimal("20.00")
    assert linhas[0].new_price == Decimal("25.00")
    assert linhas[0].product_code == "PRD-004"


def test_a_demonstracao_registra_a_mudanca_de_custo():
    produtos, historico = repositorios_demo()
    editar(produtos, cost="R$ 9,00")

    linhas = historico.list_price_edits()

    assert len(linhas) == 1
    assert linhas[0].field is PriceEditField.BUY_PRICE
    assert linhas[0].old_price == Decimal("8.00")
    assert linhas[0].new_price == Decimal("9.00")


def test_salvar_sem_mexer_nos_valores_nao_registra_nada():
    """`IS DISTINCT FROM` do trigger: salvar não é alterar.

    O formulário manda a tela inteira, então "igual ao atual" é o caso comum.
    Registrar aqui encheria o histórico de linhas que não dizem nada.
    """
    produtos, historico = repositorios_demo()
    editar(produtos, name="Cabo HDMI 2m (novo nome)")

    assert historico.list_price_edits() == ()


def test_preco_e_custo_no_mesmo_salvamento_viram_duas_linhas():
    produtos, historico = repositorios_demo()
    editar(produtos, sale_price="R$ 25,00", cost="R$ 9,00")

    linhas = historico.list_price_edits()

    assert len(linhas) == 2
    assert {l.field for l in linhas} == {
        PriceEditField.SELL_PRICE, PriceEditField.BUY_PRICE
    }


def test_duas_linhas_do_mesmo_instante_nao_embaralham_entre_consultas():
    """O que o desempate compra é estabilidade, não um "mais recente".

    Preço e custo salvos juntos acontecem no mesmo instante: entre eles não
    existe ordem cronológica. O que não pode é a tela mostrar uma ordem agora
    e outra no próximo carregamento.
    """
    produtos, historico = repositorios_demo()
    editar(produtos, sale_price="R$ 25,00", cost="R$ 9,00")

    assert historico.list_price_edits() == historico.list_price_edits()


def test_a_demonstracao_lista_do_mais_recente_para_o_mais_antigo():
    produtos, historico = repositorios_demo()
    editar(produtos, sale_price="R$ 25,00")
    editar(produtos, sale_price="R$ 30,00")

    linhas = historico.list_price_edits()

    assert [l.new_price for l in linhas] == [Decimal("30.00"), Decimal("25.00")]


def test_a_demonstracao_filtra_por_produto():
    produtos, historico = repositorios_demo()
    editar(produtos, sale_price="R$ 25,00")

    assert historico.list_price_edits("PRD-004") != ()
    assert historico.list_price_edits("PRD-999") == ()


# -------------------------------------------------------------- Supabase


def cliente_com_historico(linhas):
    return ClienteFalso(catalogo_falso(), rpc_resultados={"fn_list_price_edits": linhas})


def linha_crua(**kwargs):
    base = {
        "changed_on": "2026-10-15T14:30:00+00:00",
        "product_id": PRODUTO_ID,
        "product_code": "PRD-004",
        "product_name": "Cabo HDMI 2m",
        "field": "SELL_PRICE",
        "old_price": "20.00",
        "new_price": "25.00",
        "changed_by": "Miguel",
    }
    base.update(kwargs)
    return base


def test_o_adaptador_chama_a_funcao_com_a_empresa_e_sem_filtro():
    cliente = cliente_com_historico([linha_crua()])

    SupabasePriceHistoryRepository(cliente, COMPANY).list_price_edits()

    nome, args = cliente.chamadas_rpc[0]
    assert nome == "fn_list_price_edits"
    assert args == {"p_company_id": COMPANY, "p_product_id": None}


def test_o_adaptador_traduz_o_codigo_em_uuid_antes_de_filtrar():
    """A função exige o uuid; a tela só conhece o código.

    Filtrar por código no SQL amarraria o histórico a uma chave MUTÁVEL —
    `fn_update_products` altera `barcode`, e o rastro do produto renomeado
    sumiria da consulta justamente por ter sido alterado.
    """
    cliente = cliente_com_historico([])

    SupabasePriceHistoryRepository(cliente, COMPANY).list_price_edits("PRD-009")

    assert cliente.chamadas_rpc[0][1]["p_product_id"] == PRODUTO_ID


def test_codigo_desconhecido_nao_vira_consulta_sem_filtro():
    """Sem isto, filtrar por um produto inexistente devolveria a lista INTEIRA."""
    cliente = cliente_com_historico([linha_crua()])

    assert SupabasePriceHistoryRepository(cliente, COMPANY).list_price_edits("PRD-999") == ()
    assert cliente.chamadas_rpc == []


def test_o_adaptador_traduz_a_linha_em_mudanca():
    cliente = cliente_com_historico([linha_crua()])

    linha = SupabasePriceHistoryRepository(cliente, COMPANY).list_price_edits()[0]

    assert linha.product_code == "PRD-004"
    assert linha.field is PriceEditField.SELL_PRICE
    assert linha.old_price == Decimal("20.00")
    assert linha.new_price == Decimal("25.00")
    assert linha.changed_by == "Miguel"


def test_custo_informado_pela_primeira_vez_chega_como_ausencia():
    """`old_price` nulo é "antes não havia valor", e não zero.

    Traduzir para `Decimal(0)` aqui faria a tela mostrar "De R$ 0,00", que é
    exatamente o custo inventado que a coluna nullable existe para evitar.
    """
    cliente = cliente_com_historico([linha_crua(field="BUY_PRICE", old_price=None)])

    linha = SupabasePriceHistoryRepository(cliente, COMPANY).list_price_edits()[0]

    assert linha.old_price is None
    assert linha.new_price == Decimal("25.00")


def test_o_filtro_resolve_o_uuid_com_o_catalogo_injetado():
    """Regressão: a tela filtrada abria vazia contra o banco.

    `build_price_history_repository` INJETA o repositório de catálogo, e
    `Product` não tem uuid — `getattr(produto, "id", None)` devolvia None
    para todo código, o filtro virava "nenhum produto" e a consulta
    respondia vazio.

    O teste anterior passava porque construía o adaptador com
    `products=None`, caindo no caminho de consulta que o app nunca percorre.
    Este monta o adaptador como `backend.py` o monta.
    """
    cliente = cliente_com_historico([linha_crua()])
    catalogo = SupabaseProductRepository(cliente, COMPANY)

    linhas = SupabasePriceHistoryRepository(
        cliente, COMPANY, catalogo
    ).list_price_edits("PRD-009")

    assert cliente.chamadas_rpc, "o filtro nem chegou a consultar"
    assert cliente.chamadas_rpc[0][1]["p_product_id"] == PRODUTO_ID
    assert len(linhas) == 1


def test_produto_criado_depois_deixa_de_ser_invisivel():
    """Cachear a AUSÊNCIA tornaria permanente uma resposta temporária.

    O código some da primeira consulta só porque ainda não existia; com o
    `None` guardado no cache, o produto criado em seguida continuaria sem
    histórico até a janela ser reaberta.
    """
    cliente = cliente_com_historico([linha_crua()])
    repositorio = SupabasePriceHistoryRepository(cliente, COMPANY)

    assert repositorio.list_price_edits("PRD-NOVO") == ()

    cliente.tabelas["products"].append(
        {"id": PRODUTO_ID, "company_id": COMPANY, "barcode": "PRD-NOVO",
         "name": "Criado depois", "sell_price": "10.00", "buy_price": None,
         "unit": "UN", "stock": 0, "item_category": None, "active": True}
    )

    assert repositorio.list_price_edits("PRD-NOVO") != ()
