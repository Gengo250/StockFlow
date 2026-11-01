import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stockflow.application.dto.stock_adjustment_input import StockAdjustmentInput
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.supabase_stock_adjustment_repository import (
    SupabaseStockAdjustmentRepository,
)

from test_supabase_product_repository import (
    COMPANY,
    PRODUTO_ID,
    catalogo_falso,
    ClienteFalso,
    ErroDoPostgrest,
)


def test_adjust_confirm_chama_rpc_com_os_tipos_do_banco():
    client = ClienteFalso(
        catalogo_falso(),
        rpc_resultados={"fn_adjust_product_stock": None},
    )
    repo = SupabaseStockAdjustmentRepository(
        client, COMPANY, role=UserRole.ADMIN
    )

    entrada = StockAdjustmentInput(
        product_code="PRD-009",
        kind=MovementKind.SAIDA,
        quantity=5,
        justification="Reposição manual",
    )

    repo.adjust_confirmed(entrada)

    assert any(n == "fn_adjust_product_stock" for n, _ in client.chamadas_rpc)
    nome, args = next(
        (n, a) for n, a in client.chamadas_rpc if n == "fn_adjust_product_stock"
    )

    assert nome == "fn_adjust_product_stock"
    assert args["p_company_id"] == COMPANY
    assert args["p_product_id"] == PRODUTO_ID
    assert args["p_quantity"] == 5
    assert args["p_movement_kind"] == "SAIDA"
    assert args["p_justification"] == "Reposição manual"


def test_adjust_confirm_traduz_erro_de_permissao():
    client = ClienteFalso(
        catalogo_falso(),
        rpc_erros={
            "fn_adjust_product_stock": ErroDoPostgrest(
                "sem permissão", code="42501"
            )
        },
    )
    repo = SupabaseStockAdjustmentRepository(
        client, COMPANY, role=UserRole.STOCK
    )

    entrada = StockAdjustmentInput(
        product_code="PRD-009",
        kind=MovementKind.ENTRADA,
        quantity=1,
        justification="teste",
    )

    with pytest.raises(PermissionDeniedError):
        repo.adjust_confirmed(entrada)
