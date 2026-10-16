"""US10: uma venda leva vários produtos, com forma de pagamento e desconto.

Antes desta história, venda era sinônimo de produto: `sales` guardava um
produto em colunas próprias e vender três itens exigia abrir três vendas, sem
nada ligando uma à outra. O modelo passou a ser cabeçalho (`sales`) + itens
(`sale_items`), e a conclusão da venda dá baixa no estoque REGISTRANDO
MOVIMENTAÇÃO — a regra da US03 de que saldo é a soma das confirmadas continua
sendo a única fonte do saldo.

Os testes de tela montam o carrinho pela própria `VendasPage`; os de serviço
cobram as recusas; os de banco leem a fonte declarativa, porque não há
Postgres neste ambiente.
"""

import dataclasses
import re
from pathlib import Path

import pytest

from stockflow.application.services.sale_service import SaleService
from stockflow.infrastructure.repositories.demo_client_repository import (
    DemoClientRepository,
)
from stockflow.infrastructure.repositories.demo_product_repository import (
    DemoProductRepository,
)
from stockflow.infrastructure.repositories.demo_sale_repository import (
    DemoSaleRepository,
)
from stockflow.presentation.demo_products import DEMO_PRODUCTS

RAIZ = Path(__file__).resolve().parents[1]
CODE = RAIZ / "database" / "code"
GATILHO = CODE / "triggers" / "06_sale_completion.sql"

MONITOR = "PRD-009"      # R$ 2.499,90
TECLADO = "PRD-008"      # R$   459,90
CLIENTE_ATIVO = "Carlos Mendes"


def _com_cliente(page, nome=CLIENTE_ATIVO):
    assert page.selecionar_cliente_externo(nome) is True


def _adicionar(page, codigo, quantidade=None):
    assert page.selecionar_produto(codigo) is True
    if quantidade is not None:
        page.qtd_input.setText(str(quantidade))
    page._adicionar_item()


# ----------------------------------------------------------------- carrinho


def test_adicionar_item_mostra_o_carrinho_com_o_subtotal(vendas_page):
    assert vendas_page.itens_table.isVisibleTo(vendas_page) is False

    _adicionar(vendas_page, MONITOR, 2)

    assert vendas_page.itens_table.rowCount() == 1
    assert vendas_page.itens_table.item(0, 1).text() == "2"
    assert vendas_page.itens_table.item(0, 3).text() == "R$ 4.999,80"
    assert vendas_page.total_label.text() == "Total: R$ 4.999,80"


def test_quantidade_vazia_vale_um(vendas_page):
    _adicionar(vendas_page, MONITOR)
    assert vendas_page.itens[0]["quantidade"] == 1


def test_mesmo_produto_duas_vezes_vira_uma_linha_somada(vendas_page):
    _adicionar(vendas_page, MONITOR, 2)
    _adicionar(vendas_page, MONITOR, 3)

    assert len(vendas_page.itens) == 1
    assert vendas_page.itens[0]["quantidade"] == 5


def test_quantidade_invalida_nao_entra_no_carrinho(vendas_page):
    assert vendas_page.selecionar_produto(MONITOR) is True
    vendas_page.qtd_input.setText("0")
    vendas_page._adicionar_item()

    assert vendas_page.itens == []
    assert "quantidade" in vendas_page.warning_label.text().lower()


def test_remover_ultimo_item_esconde_o_carrinho(vendas_page):
    _adicionar(vendas_page, MONITOR, 1)
    vendas_page._remover_ultimo_item()

    assert vendas_page.itens == []
    assert vendas_page.itens_table.isVisibleTo(vendas_page) is False
    assert vendas_page.total_label.text() == ""


def test_desconto_abate_do_total_exibido(vendas_page):
    _adicionar(vendas_page, MONITOR, 1)
    vendas_page.desconto_input.setText("499,90")
    vendas_page._atualizar_carrinho()

    assert vendas_page.total_label.text() == "Total: R$ 2.000,00"


def test_desconto_meio_digitado_nao_apaga_o_total(vendas_page):
    """O operador está olhando para o total enquanto digita o desconto."""
    _adicionar(vendas_page, MONITOR, 1)
    vendas_page.desconto_input.setText("1.")
    vendas_page._atualizar_carrinho()

    assert vendas_page.total_label.text() == "Total: R$ 2.499,90"


# --------------------------------------------------------------- gravação


def test_finalizar_com_carrinho_grava_uma_venda_com_todos_os_itens(vendas_page):
    antes = len(vendas_page.historico_vendas)
    _com_cliente(vendas_page)
    _adicionar(vendas_page, MONITOR, 1)
    _adicionar(vendas_page, TECLADO, 2)

    vendas_page._registrar_venda()

    assert len(vendas_page.historico_vendas) == antes + 1
    nova = vendas_page.historico_vendas[0]
    assert nova["produto"] == "2 itens"
    assert nova["total"] == "3419.70"          # 2499,90 + 2 x 459,90
    assert vendas_page.itens == []


def test_finalizar_com_um_item_no_carrinho_descreve_o_produto(vendas_page):
    _com_cliente(vendas_page)
    _adicionar(vendas_page, TECLADO, 3)

    vendas_page._registrar_venda()

    assert vendas_page.historico_vendas[0]["produto"] == "3x Teclado mecânico sem fio"
    assert vendas_page.historico_vendas[0]["produto_codigo"] == TECLADO


def test_carrinho_vazio_mantem_a_venda_de_um_produto(vendas_page):
    """O caminho antigo não pode exigir carrinho para vender uma coisa."""
    antes = len(vendas_page.historico_vendas)
    _com_cliente(vendas_page)
    assert vendas_page.selecionar_produto(MONITOR) is True
    vendas_page.val_input.setText("100,00")

    vendas_page._registrar_venda()

    assert len(vendas_page.historico_vendas) == antes + 1
    assert vendas_page.historico_vendas[0]["total"] == "100.00"


def test_venda_com_itens_exige_cliente(vendas_page):
    _adicionar(vendas_page, MONITOR, 1)
    vendas_page._registrar_venda()

    assert vendas_page.historico_vendas[:1] != [vendas_page.itens]
    assert "cliente" in vendas_page.warning_label.text().lower()
    assert vendas_page.itens != []          # o carrinho sobrevive à recusa


# ---------------------------------------------------------------- serviço


@pytest.fixture
def service():
    return SaleService(
        DemoSaleRepository(), DemoClientRepository(),
        DemoProductRepository(dict(DEMO_PRODUCTS)),
    )


@pytest.fixture
def sessao_de_venda():
    from stockflow.domain.enums.user_role import UserRole
    from stockflow.presentation.demo_accounts import conta_por_papel

    return conta_por_papel(UserRole.SELLER).session()


def _itens(*pares):
    return [{"codigo": c, "quantidade": q} for c, q in pares]


def test_servico_recusa_venda_sem_item(service, sessao_de_venda):
    cliente = DemoClientRepository().list_all()[0]
    with pytest.raises(ValueError, match="ao menos um item"):
        service.register_sale(sessao_de_venda, cliente.client_id, [])


def test_servico_recusa_forma_de_pagamento_desconhecida(service, sessao_de_venda):
    cliente = next(c for c in DemoClientRepository().list_all() if c.active)
    with pytest.raises(ValueError, match="forma de pagamento"):
        service.register_sale(sessao_de_venda, cliente.client_id,
                              _itens((MONITOR, 1)), payment_method="BITCOIN")


def test_servico_recusa_desconto_maior_que_o_total(service, sessao_de_venda):
    cliente = next(c for c in DemoClientRepository().list_all() if c.active)
    with pytest.raises(ValueError, match="desconto"):
        service.register_sale(sessao_de_venda, cliente.client_id,
                              _itens((TECLADO, 1)), discount="10000,00")


def test_servico_recusa_produto_inativo(sessao_de_venda):
    """Mesma regra da US02, agora para cada item do carrinho."""
    catalogo = dict(DEMO_PRODUCTS)
    catalogo[MONITOR] = dataclasses.replace(catalogo[MONITOR], active=False)
    service = SaleService(
        DemoSaleRepository(), DemoClientRepository(),
        DemoProductRepository(catalogo),
    )

    cliente = next(c for c in DemoClientRepository().list_all() if c.active)
    with pytest.raises(ValueError, match="produto ativo"):
        service.register_sale(sessao_de_venda, cliente.client_id,
                              _itens((MONITOR, 1)))


def test_um_item_inativo_derruba_a_venda_inteira(sessao_de_venda):
    """Venda parcial é pior que recusa: o operador cobraria o carrinho todo."""
    catalogo = dict(DEMO_PRODUCTS)
    catalogo[TECLADO] = dataclasses.replace(catalogo[TECLADO], active=False)
    repositorio = DemoSaleRepository()
    service = SaleService(
        repositorio, DemoClientRepository(), DemoProductRepository(catalogo),
    )

    cliente = next(c for c in DemoClientRepository().list_all() if c.active)
    antes = len(repositorio.list_all())
    with pytest.raises(ValueError):
        service.register_sale(sessao_de_venda, cliente.client_id,
                              _itens((MONITOR, 1), (TECLADO, 1)))

    assert len(repositorio.list_all()) == antes


# ------------------------------------------------------ baixa de estoque


def test_conclusao_da_venda_vira_movimentacao_de_saida_ligada_a_venda():
    gatilho = GATILHO.read_text(encoding="utf-8")
    insercao = re.search(
        r"INSERT INTO public\.stock_movements\s*\((.*?)\)\s*VALUES\s*\((.*?)\);",
        gatilho, re.S | re.I,
    )
    assert insercao, "a conclusão da venda não registra movimentação"
    colunas = insercao.group(1).lower()
    valores = insercao.group(2).upper()

    assert "sale_id" in colunas, "a movimentação não guarda de qual venda veio"
    assert "'SAIDA'" in valores
    assert "'CONFIRMADA'" in valores


def test_conclusao_da_venda_nao_escreve_products_stock():
    """Saldo é a soma das confirmadas; escrever o campo direto é desfeito."""
    gatilho = re.sub(r"--[^\n]*", "", GATILHO.read_text(encoding="utf-8"))
    assert not re.search(
        r"UPDATE\s+public\.products\s+SET\s+stock\s*=", gatilho, re.I
    )


def test_conclusao_da_venda_confere_o_saldo_antes_de_baixar():
    gatilho = re.sub(r"--[^\n]*", "", GATILHO.read_text(encoding="utf-8"))
    conferencia = re.search(r"fn_confirmed_balance", gatilho)
    insercao = re.search(r"INSERT INTO public\.stock_movements", gatilho, re.I)
    assert conferencia and insercao
    assert conferencia.start() < insercao.start(), (
        "a movimentação é inserida antes de conferir o saldo"
    )


def test_gatilho_dispara_so_na_transicao_para_concluida():
    gatilho = GATILHO.read_text(encoding="utf-8")
    assert re.search(
        r"WHEN \(OLD\.status IS DISTINCT FROM NEW\.status\s+AND NEW\.status = 'CONCLUIDA'\)",
        gatilho,
    )
