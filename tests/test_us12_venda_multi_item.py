from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from PySide6.QtWidgets import QLabel

from stockflow.application.dto.sale_item import SaleItemInput
from stockflow.application.services.sale_service import (
    calculate_total_from_items,
    parse_total,
)
from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.pages.vendas import VendasPage
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.presentation.windows.main_window import MainWindow


@pytest.fixture
def page(qapp):
    return VendasPage(
        products=dict(DEMO_PRODUCTS),
        session=conta_por_papel(UserRole.SELLER).session(),
    )


def test_total_usa_decimal_e_precos_atuais_do_catalogo(page):
    assert parse_total("R$ 2.499,90") == Decimal("2499.90")
    items = (
        SaleItemInput("PRD-009", 1),
        SaleItemInput("PRD-008", 2),
    )
    assert calculate_total_from_items(
        items,
        {"PRD-009": Decimal("2499.90"), "PRD-008": Decimal("459.90")},
    ) == Decimal("3419.70")


@pytest.mark.parametrize("value", ["-1,00", "1,234", "abc", "1.2.3"])
def test_preco_invalido_nao_e_convertido_em_zero(value):
    with pytest.raises(ValueError):
        parse_total(value)


def test_interface_recalcula_total_a_cada_linha_e_quantidade(page):
    page.selecionar_cliente_externo("Ana Ferreira")
    for code, quantity in (("PRD-009", 1), ("PRD-008", 2)):
        assert page.selecionar_produto(code)
        page.qtd_input.setText(str(quantity))
        page._adicionar_item()

    assert page.total_label.text() == "Total: R$ 3.419,70"
    assert page.itens_table.item(0, 3).text() == "R$ 2.499,90"
    assert page.itens_table.item(1, 3).text() == "R$ 919,80"
    assert [(item["codigo"], item["quantidade"]) for item in page.itens] == [
        ("PRD-009", 1),
        ("PRD-008", 2),
    ]


def test_editar_e_remover_linha_nao_mexe_nas_outras(page):
    for code, quantity in (("PRD-009", 2), ("PRD-008", 2), ("PRD-007", 1)):
        assert page.selecionar_produto(code)
        page.qtd_input.setText(str(quantity))
        page._adicionar_item()
    page._remover_ultimo_item()

    assert [(item["codigo"], item["quantidade"]) for item in page.itens] == [
        ("PRD-009", 2),
        ("PRD-008", 2),
    ]
    assert page.total_label.text() == "Total: R$ 5.919,60"


def test_confirmacao_grava_venda_e_saida_de_estoque(page):
    page.selecionar_cliente_externo("Ana Ferreira")
    for code, quantity in (("PRD-009", 1), ("PRD-008", 2)):
        assert page.selecionar_produto(code)
        page.qtd_input.setText(str(quantity))
        page._adicionar_item()

    page._registrar_venda()

    assert len(page.historico_vendas) == 3
    assert page.historico_vendas[0]["valor"] == "R$ 3.419,70"
    assert page.products["PRD-009"].stock == "17"
    assert page.products["PRD-008"].stock == "4"
    assert len(page.movement_repository.list_movements()) == 2
    assert all(
        row["note"].startswith("SAIDA_VENDA")
        and row["status"] == "CONFIRMADA"
        for row in page.movement_repository._movements
    )
    assert page.cliente_combo.currentIndex() == 0
    assert page.itens == []


def test_venda_atualiza_visualmente_as_abas_de_produtos_e_estoque(qapp):
    window = MainWindow(conta_por_papel(UserRole.SELLER).session())
    try:
        page = window.vendas_page
        assert page.selecionar_cliente_externo("Ana Ferreira")
        assert page.selecionar_produto("PRD-009")
        page.qtd_input.setText("1")
        page._adicionar_item()

        page._registrar_venda()

        assert window.products["PRD-009"].stock == "17"
        stock_row = next(
            row for row in range(window.estoque_page.table.rowCount())
            if window.estoque_page.table.item(row, 0).text() == "PRD-009"
        )
        assert window.estoque_page.table.item(stock_row, 3).text() == "17"
        card_stock_values = [
            label.text()
            for label in window.products_page.cards["PRD-009"].findChildren(
                QLabel
            )
            if label.objectName() == "productCaption"
        ]
        assert "17" in card_stock_values
    finally:
        window.close()


def test_falha_em_um_item_nao_grava_venda_nem_movimentacao(page):
    client_id = page.client_repository.get("CLI-001").client_id
    before_stock = {
        code: page.products[code].stock for code in ("PRD-009", "PRD-006")
    }
    before_sales = len(page.service.repository.list_all())
    before_movements = len(page.movement_repository.list_movements())

    with pytest.raises(ValueError, match="Estoque insuficiente"):
        page.service.register_sale(
            page.session,
            client_id,
            [
                {"codigo": "PRD-009", "quantidade": 1},
                {"codigo": "PRD-006", "quantidade": 1},
            ],
        )

    assert {code: page.products[code].stock for code in before_stock} == before_stock
    assert len(page.service.repository.list_all()) == before_sales
    assert len(page.movement_repository.list_movements()) == before_movements


def test_linhas_duplicadas_sao_validadas_pelo_total_da_quantidade(page):
    client_id = page.client_repository.get("CLI-001").client_id
    with pytest.raises(ValueError, match="Estoque insuficiente"):
        page.service.register_sale(
            page.session,
            client_id,
            [
                {"codigo": "PRD-007", "quantidade": 2},
                {"codigo": "PRD-007", "quantidade": 1},
            ],
        )


def test_linhas_duplicadas_gravam_uma_saida_por_linha(page):
    page.selecionar_cliente_externo("Ana Ferreira")
    for quantity in (1, 1):
        assert page.selecionar_produto("PRD-009")
        page.qtd_input.setText(str(quantity))
        page._adicionar_item()

    page._registrar_venda()

    assert page.historico_vendas[0]["itens_count"] == 1
    assert page.products["PRD-009"].stock == "16"
    assert len(page.movement_repository.list_movements()) == 1


def test_vendas_concorrentes_nao_ultrapassam_saldo_disponivel(page):
    client_id = page.client_repository.get("CLI-001").client_id
    barrier = Barrier(2)

    def register():
        barrier.wait()
        try:
            page.service.register_sale(
                page.session,
                client_id,
                [{"codigo": "PRD-007", "quantidade": 2}],
            )
            return "registered"
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _index: register(), range(2)))

    assert results.count("registered") == 1
    assert sum("Estoque insuficiente" in result for result in results) == 1
    assert page.products["PRD-007"].stock == "0"
    assert len(page.service.repository.list_all()) == 3
    assert len(page.movement_repository.list_movements()) == 1


def test_confirmacao_sem_itens_fica_bloqueada(page):
    page.selecionar_cliente_externo("Ana Ferreira")
    page._registrar_venda()

    assert len(page.historico_vendas) == 2
    assert "produto ativo" in page.warning_label.text().lower()
