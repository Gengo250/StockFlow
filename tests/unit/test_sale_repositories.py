"""Os dois adaptadores satisfazem a MESMA semântica (US17).

Se o de demonstração mentir sobre filtro, ordem ou paginação, os testes de
interface validam ficção: a tela passa verde contra um comportamento que o
banco não tem. Este arquivo existe para que a divergência fique vermelha
aqui, e não na primeira gravação real.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from stockflow.application.dto.sale_filter import SaleFilter
from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.infrastructure.repositories.demo_sale_repository import (
    DemoSaleRepository,
)


def linha(i):
    return dict(
        id=f"VND-{i:04d}",
        cliente=f"Cliente {i % 5}",
        produto="Produto",
        valor="R$ 10,00",
        data=f"{(i % 28) + 1:02d}/10/2026 10:00",
        total=f"{10 + i}.00",
        itens_count=1,
        status="CONCLUIDA",
        seller="Vendedor",
        seller_id="s1",
        client_id=f"c{i % 5}",
        payment_method="PIX",
        discount="0",
        items=[],
    )


@pytest.fixture
def repositorio():
    repo = DemoSaleRepository()
    repo.rows = [linha(i) for i in range(120)]
    return repo


def cliente_falso():
    return SimpleNamespace(name="Ana", client_id="c1")


def test_pagina_devolve_o_tamanho_pedido_e_o_total_filtrado(repositorio):
    pagina = repositorio.list_page(SaleFilter(), page=1, size=50)
    assert len(pagina.rows) == 50
    assert pagina.total == 120
    assert pagina.pages == 3


def test_paginacao_nao_repete_nem_pula_registro(repositorio):
    vistos = []
    for numero in (1, 2, 3):
        vistos += [l["id"] for l in repositorio.list_page(SaleFilter(), numero, 50).rows]
    assert len(vistos) == 120
    assert len(set(vistos)) == 120


def test_pagina_alem_do_fim_vem_vazia_sem_estourar(repositorio):
    assert repositorio.list_page(SaleFilter(), page=99, size=50).rows == ()


def test_filtro_por_cliente_muda_o_total(repositorio):
    pagina = repositorio.list_page(SaleFilter(client_id="c1"), 1, 50)
    assert pagina.total == 24
    assert all(l["client_id"] == "c1" for l in pagina.rows)


def test_filtros_combinam(repositorio):
    repositorio.rows[5]["status"] = "CANCELADA"
    pagina = repositorio.list_page(
        SaleFilter(client_id="c0", status="CANCELADA"), 1, 50
    )
    assert pagina.total == 1
    assert pagina.rows[0]["id"] == "VND-0005"


def test_filtro_por_id_casa_por_prefixo(repositorio):
    pagina = repositorio.list_page(SaleFilter(sale_id="VND-0007"), 1, 50)
    assert [l["id"] for l in pagina.rows] == ["VND-0007"]


def test_filtro_de_periodo_inclui_o_ultimo_dia(repositorio):
    """"Até dia 5" inclui o dia 5 inteiro — o erro clássico do limite."""
    pagina = repositorio.list_page(
        SaleFilter(date_from=date(2026, 10, 5), date_to=date(2026, 10, 5)), 1, 50
    )
    assert pagina.total > 0
    assert all(l["data"].startswith("05/10/2026") for l in pagina.rows)


def test_ordem_padrao_e_da_mais_recente_para_a_mais_antiga(repositorio):
    pagina = repositorio.list_page(SaleFilter(), 1, 3)
    datas = [l["data"][:10] for l in pagina.rows]
    assert datas == sorted(datas, reverse=True)


def test_ordenacao_por_valor_decrescente(repositorio):
    repositorio.rows[7]["total"] = "999.00"
    pagina = repositorio.list_page(SaleFilter(sort="VALOR_DESC"), 1, 5)
    assert pagina.rows[0]["total"] == "999.00"


def test_ordenacao_por_cliente(repositorio):
    pagina = repositorio.list_page(SaleFilter(sort="CLIENTE_ASC"), 1, 5)
    assert pagina.rows[0]["cliente"] == "Cliente 0"


def test_get_devolve_none_para_venda_inexistente(repositorio):
    assert repositorio.get("NAO-EXISTE") is None


def test_cancelar_marca_a_venda_e_devolve_o_saldo():
    repo = DemoSaleRepository()
    antes = int(repo._products["PRD-009"].stock)
    venda = repo.register_multiple(
        cliente_falso(), (SaleItemInput("PRD-009", 2),), Decimal("20.00")
    )
    assert int(repo._products["PRD-009"].stock) == antes - 2

    repo.cancel(venda["id"], "registro em duplicidade")

    assert repo.get(venda["id"])["status"] == "CANCELADA"
    assert int(repo._products["PRD-009"].stock) == antes


def test_devolver_marca_a_venda_e_devolve_o_saldo():
    repo = DemoSaleRepository()
    antes = int(repo._products["PRD-009"].stock)
    venda = repo.register_multiple(
        cliente_falso(), (SaleItemInput("PRD-009", 3),), Decimal("30.00")
    )
    repo.revert(venda["id"], "cliente desistiu")

    gravada = repo.get(venda["id"])
    assert gravada["status"] == "DEVOLVIDA"
    assert gravada["reversal_kind"] == "DEVOLUCAO"
    assert gravada["reversal_reason"] == "cliente desistiu"
    assert int(repo._products["PRD-009"].stock) == antes


def test_cancelamento_anula_a_saida_enquanto_devolucao_grava_entrada():
    """A diferença entre as duas espécies tem que sobreviver no histórico."""
    repo = DemoSaleRepository()
    cancelada = repo.register_multiple(
        cliente_falso(), (SaleItemInput("PRD-009", 1),), Decimal("10.00")
    )
    devolvida = repo.register_multiple(
        cliente_falso(), (SaleItemInput("PRD-009", 1),), Decimal("10.00")
    )
    repo.cancel(cancelada["id"], "engano")
    repo.revert(devolvida["id"], "defeito")

    movimentos = repo.movements.list_movements()
    da_cancelada = [m for m in movimentos if str(m[0]) and cancelada["id"] in str(m)]
    assert any("Cancelada" in str(m) for m in da_cancelada)
    assert any("DEVOLUCAO_VENDA" in str(m) for m in movimentos)


def test_venda_revertida_nao_reverte_de_novo():
    repo = DemoSaleRepository()
    venda = repo.register_multiple(
        cliente_falso(), (SaleItemInput("PRD-009", 1),), Decimal("10.00")
    )
    repo.cancel(venda["id"], "engano")
    with pytest.raises(ValueError, match="já foi"):
        repo.revert(venda["id"], "tentativa dupla")


def test_reverter_venda_inexistente_e_recusado():
    repo = DemoSaleRepository()
    with pytest.raises(ValueError, match="não encontrada"):
        repo.cancel("NAO-EXISTE", "tentativa")


def test_supabase_monta_a_chamada_com_todos_os_filtros():
    """O adaptador traduz o filtro inteiro, inclusive o limite exclusivo."""
    from stockflow.infrastructure.repositories.supabase_sale_repository import (
        SupabaseSaleRepository,
    )

    class API:
        def __init__(self):
            self.args = None

        def rpc(self, nome, args):
            self.nome, self.args = nome, args
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=[]))

    api = API()
    SupabaseSaleRepository(api, "empresa-1").list_page(
        SaleFilter(
            sale_id="abc",
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 5),
            client_id="c1",
            seller_id="s1",
            status="CANCELADA",
            sort="VALOR_DESC",
        ),
        page=3,
        size=25,
    )
    assert api.nome == "fn_list_sales"
    assert api.args["p_sale_id"] == "abc"
    assert api.args["p_from"] == "2026-10-01"
    # Limite superior EXCLUSIVO: dia 5 inclusivo vira "antes do dia 6".
    assert api.args["p_to"] == "2026-10-06"
    assert api.args["p_client_id"] == "c1"
    assert api.args["p_seller_id"] == "s1"
    assert api.args["p_status"] == "CANCELADA"
    assert api.args["p_sort"] == "VALOR_DESC"
    assert api.args["p_limit"] == 25
    assert api.args["p_offset"] == 50


def test_supabase_le_o_total_da_propria_consulta():
    from stockflow.infrastructure.repositories.supabase_sale_repository import (
        SupabaseSaleRepository,
    )

    dados = [{
        "id": "s1", "client_id": "c1", "client_name": "Ana", "seller_id": "u1",
        "seller_name": "João", "payment_method": "PIX", "discount": 0,
        "total": 10, "status": "DEVOLVIDA", "created_on": "2026-10-05T10:00:00Z",
        "items": [{"product_code": "P1", "product_name": "Produto", "quantity": 1}],
        "reversal_kind": "DEVOLUCAO", "reversal_reason": "defeito",
        "reversal_on": "2026-10-06T10:00:00Z", "reversal_by_name": "Maria",
        "total_count": 97,
    }]

    class API:
        def rpc(self, nome, args):
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=dados))

    pagina = SupabaseSaleRepository(API(), "empresa-1").list_page(SaleFilter(), 1, 50)
    assert pagina.total == 97
    assert pagina.pages == 2
    linha_lida = pagina.rows[0]
    assert linha_lida["status"] == "DEVOLVIDA"
    assert linha_lida["seller"] == "João"
    assert linha_lida["reversal_kind"] == "DEVOLUCAO"
    assert linha_lida["reversal_by"] == "Maria"


def test_supabase_sem_linha_reporta_total_zero():
    from stockflow.infrastructure.repositories.supabase_sale_repository import (
        SupabaseSaleRepository,
    )

    class API:
        def rpc(self, nome, args):
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=[]))

    pagina = SupabaseSaleRepository(API(), "empresa-1").list_page(SaleFilter(), 1, 50)
    assert pagina.total == 0
    assert pagina.pages == 1


def test_supabase_reversao_chama_a_funcao_certa():
    from stockflow.infrastructure.repositories.supabase_sale_repository import (
        SupabaseSaleRepository,
    )

    chamadas = []

    class API:
        def rpc(self, nome, args):
            chamadas.append((nome, args))
            return SimpleNamespace(execute=lambda: SimpleNamespace(data={"status": "ok"}))

    repo = SupabaseSaleRepository(API(), "empresa-1")
    repo.cancel("s1", "engano")
    repo.revert("s2", "defeito")
    assert chamadas[0] == ("fn_cancel_sale", {"p_sale_id": "s1", "p_reason": "engano"})
    assert chamadas[1] == ("fn_return_sale", {"p_sale_id": "s2", "p_reason": "defeito"})
