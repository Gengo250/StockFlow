"""Comprovante de venda (US19/SCRUM-213).

A história pede um documento a partir do que JÁ está gravado. Estes testes
fixam as duas coisas que isso implica: o comprovante reflete o snapshot da
venda, e emitir não toca em nada.
"""

from decimal import Decimal

import pytest

from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.domain.sale_receipt import (
    ReceiptCompany,
    ReceiptNotAvailable,
    build_sale_receipt,
)

EMPRESA = ReceiptCompany(name="StockFlow Comércio LTDA", document="11222333000181")

VENDA = {
    "id": "3f2a7c41-0000-4000-8000-000000000001",
    "cliente": "Ana Ferreira",
    "seller": "juliana.ramos",
    "data": "31/10/2026 14:22",
    "status": "CONCLUIDA",
    "payment_method": "PIX",
    "discount": "11.00",
    "original_total": "90.00",
    "total": "79.00",
    "valor": "R$ 79,00",
    "items": [
        {"product_code": "PRD-001", "product_name": "Teclado", "quantity": 2,
         "unit_price": "30.00", "subtotal": "60.00",
         "discount_amount": "6.00", "final_subtotal": "54.00"},
        {"product_code": "PRD-002", "product_name": "Mouse", "quantity": 1,
         "unit_price": "30.00", "subtotal": "30.00",
         "discount_amount": "0.00", "final_subtotal": "30.00"},
    ],
}


def test_venda_confirmada_gera_comprovante_com_todos_os_dados_obrigatorios():
    comprovante = build_sale_receipt(VENDA, EMPRESA)

    assert comprovante.sale_id == VENDA["id"]
    assert comprovante.issued_on == "31/10/2026 14:22"
    assert comprovante.company == EMPRESA
    assert comprovante.client == "Ana Ferreira"
    assert comprovante.seller == "juliana.ramos"
    assert comprovante.status is SaleStatus.CONCLUIDA
    assert comprovante.payment.method == "PIX"
    assert comprovante.payment.amount == Decimal("79.00")
    assert len(comprovante.items) == 2


def test_venda_pendente_nao_emite_comprovante_definitivo():
    """SCRUM-227: carrinho em montagem não é operação realizada."""
    with pytest.raises(ReceiptNotAvailable) as erro:
        build_sale_receipt(VENDA | {"status": "PENDENTE"}, EMPRESA)
    assert "não foi confirmada" in str(erro.value)


def test_itens_preservam_quantidade_preco_e_desconto_gravados():
    teclado, mouse = build_sale_receipt(VENDA, EMPRESA).items

    assert (teclado.code, teclado.name) == ("PRD-001", "Teclado")
    assert teclado.quantity == 2
    assert teclado.unit_price == Decimal("30.00")
    assert teclado.subtotal == Decimal("60.00")
    assert teclado.discount == Decimal("6.00")
    assert teclado.final_subtotal == Decimal("54.00")
    assert mouse.discount == Decimal("0.00")


def test_totais_separam_desconto_de_item_e_desconto_da_venda():
    """`sales.discount` é o desconto TOTAL; a diferença é o do cabeçalho."""
    comprovante = build_sale_receipt(VENDA, EMPRESA)

    assert comprovante.gross == Decimal("90.00")
    assert comprovante.item_discount == Decimal("6.00")
    assert comprovante.sale_discount == Decimal("5.00")
    assert comprovante.total_discount == Decimal("11.00")
    assert comprovante.net == Decimal("79.00")


def test_venda_sem_cliente_associado_omite_o_bloco_do_cliente():
    comprovante = build_sale_receipt(VENDA | {"cliente": ""}, EMPRESA)
    assert comprovante.client is None


def test_venda_cancelada_emite_comprovante_marcado_com_o_motivo():
    """SCRUM-229: cancelada FOI confirmada, então emite — marcada."""
    cancelada = VENDA | {
        "status": "CANCELADA",
        "reversal_kind": "CANCELAMENTO",
        "reversal_reason": "Registro em duplicidade",
        "reversal_on": "31/10/2026 15:00",
        "reversal_by": "ana.ferreira",
    }
    comprovante = build_sale_receipt(cancelada, EMPRESA)

    assert comprovante.cancelado
    assert comprovante.status is SaleStatus.CANCELADA
    assert comprovante.cancellation.reason == "Registro em duplicidade"
    assert comprovante.cancellation.by == "ana.ferreira"
    # Os dados comerciais continuam os da operação original.
    assert comprovante.net == Decimal("79.00")
    assert len(comprovante.items) == 2


def test_venda_devolvida_tambem_emite_marcada():
    devolvida = VENDA | {
        "status": "DEVOLVIDA",
        "reversal_kind": "DEVOLUCAO",
        "reversal_reason": "Cliente desistiu",
        "reversal_on": "31/10/2026 16:00",
        "reversal_by": "ana.ferreira",
    }
    assert build_sale_receipt(devolvida, EMPRESA).cancelado


def test_venda_sem_itens_nao_emite_comprovante():
    with pytest.raises(ReceiptNotAvailable):
        build_sale_receipt(VENDA | {"items": []}, EMPRESA)


def test_valor_corrompido_recusa_a_emissao_em_vez_de_inventar_numero():
    with pytest.raises(ReceiptNotAvailable):
        build_sale_receipt(VENDA | {"total": "noventa reais"}, EMPRESA)


def test_descontos_que_nao_reconciliam_recusam_a_emissao():
    """Desconto maior que o bruto é dado inconsistente, não comprovante."""
    with pytest.raises(ReceiptNotAvailable):
        build_sale_receipt(VENDA | {"discount": "900.00"}, EMPRESA)


def test_construir_o_comprovante_nao_altera_a_venda_de_origem():
    """Regra 6: emitir é leitura. O dicionário de entrada sai intacto."""
    original = {chave: valor for chave, valor in VENDA.items()}
    build_sale_receipt(VENDA, EMPRESA)
    assert VENDA == original


# --------------------------------------------------- serviço de emissão

from stockflow.application.services.receipt_service import ReceiptService
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_sale_repository import (
    DemoSaleRepository,
)
from stockflow.presentation.demo_accounts import conta_por_papel


class _VendasFalsas:
    """Dublê do `SaleService`: registra as chamadas e nunca grava."""

    def __init__(self, venda):
        self._venda, self.consultas = venda, []

    def get_sale(self, session, sale_id):
        self.consultas.append((session, sale_id))
        return self._venda


class _EmpresaFixa:
    def __init__(self, empresa=EMPRESA):
        self._empresa = empresa

    def get_profile(self):
        return self._empresa


def _admin():
    return conta_por_papel(UserRole.ADMIN).session()


def _vendedor():
    return conta_por_papel(UserRole.SELLER).session()


def test_servico_emite_pelo_mesmo_caminho_de_leitura_da_us17():
    vendas = _VendasFalsas(VENDA)
    comprovante = ReceiptService(vendas, _EmpresaFixa()).issue(
        _vendedor(), VENDA["id"]
    )

    assert comprovante.sale_id == VENDA["id"]
    assert comprovante.company == EMPRESA
    # Uma consulta por emissão: nada de reler cliente, produto ou vendedor.
    assert len(vendas.consultas) == 1


def test_servico_recusa_quem_nao_pode_ver_vendas():
    class _SemPapel:
        role = None
        user_id = "x"

    with pytest.raises(PermissionDeniedError):
        ReceiptService(_VendasFalsas(VENDA), _EmpresaFixa()).issue(
            _SemPapel(), VENDA["id"]
        )


def test_servico_recusa_venda_inexistente():
    with pytest.raises(ReceiptNotAvailable):
        ReceiptService(_VendasFalsas(None), _EmpresaFixa()).issue(_admin(), "sumiu")


def test_servico_recusa_identificador_vazio():
    with pytest.raises(ReceiptNotAvailable):
        ReceiptService(_VendasFalsas(VENDA), _EmpresaFixa()).issue(_admin(), "")


def test_servico_recusa_venda_pendente():
    vendas = _VendasFalsas(VENDA | {"status": "PENDENTE"})
    with pytest.raises(ReceiptNotAvailable):
        ReceiptService(vendas, _EmpresaFixa()).issue(_admin(), VENDA["id"])


def test_servico_nao_expoe_nenhum_caminho_de_escrita():
    """Regra 6/7 por construção: o serviço não conhece método que grava."""
    publicos = [nome for nome in dir(ReceiptService) if not nome.startswith("_")]
    assert publicos == ["issue"]


def test_emitir_e_reemitir_nao_mudam_venda_estoque_nem_pagamentos():
    """Regra 4 e 6 contra o repositório de verdade do modo demonstração."""
    from stockflow.application.dto.sale_item import SaleItemInput
    from stockflow.application.services.sale_service import parse_price
    from stockflow.domain.entities.client import Client
    from stockflow.presentation.demo_products import DEMO_PRODUCTS

    catalogo = dict(DEMO_PRODUCTS)
    repositorio = DemoSaleRepository(catalogo)
    codigo = next(iter(catalogo))
    venda = repositorio.register_multiple(
        Client(client_id="CLI-1", name="Ana Ferreira"),
        (SaleItemInput(codigo, 1),),
        parse_price(catalogo[codigo].sale_price),
        seller_id="USR-004",
    )

    class _Vendas:
        def get_sale(self, session, sale_id):
            return repositorio.get(sale_id)

    servico = ReceiptService(_Vendas(), _EmpresaFixa())
    antes = repositorio.get(venda["id"])
    saldo_antes = catalogo[codigo].stock
    historico_antes = len(repositorio.list_all())

    primeiro = servico.issue(_admin(), venda["id"])
    segundo = servico.issue(_admin(), venda["id"])

    assert primeiro == segundo
    assert repositorio.get(venda["id"]) == antes
    assert catalogo[codigo].stock == saldo_antes
    assert len(repositorio.list_all()) == historico_antes


def test_reemissao_preserva_o_nome_gravado_quando_o_cadastro_muda_depois():
    """SCRUM-228: o snapshot da venda é a fonte, não o cadastro atual."""
    vendas = _VendasFalsas(VENDA)
    servico = ReceiptService(vendas, _EmpresaFixa())
    primeiro = servico.issue(_admin(), VENDA["id"])

    # O cadastro do cliente muda; a venda gravada não.
    reemitido = servico.issue(_admin(), VENDA["id"])

    assert reemitido.client == primeiro.client == "Ana Ferreira"
    assert reemitido.items == primeiro.items
    assert reemitido.net == primeiro.net
