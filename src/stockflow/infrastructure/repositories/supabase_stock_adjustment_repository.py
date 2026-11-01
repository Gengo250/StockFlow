"""Adaptador de ajuste manual sobre o Supabase.

Chama a RPC `public.fn_adjust_product_stock` (histórico + saldo via
trigger), garantindo a mesma tradução de erro de permissão usada pelos
adaptadores de movimentação.
"""

from stockflow.application.dto.stock_adjustment_input import (
    StockAdjustmentInput,
)
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.application.ports.stock_adjustment_repository import (
    StockAdjustmentRepository,
)
from stockflow.infrastructure.repositories.supabase_product_repository import (
    _e_recusa_de_permissao,
    PERMISSION_SQLSTATE,
)


ACTION_BY_RPC = {
    "fn_adjust_product_stock": "ajustar saldo do estoque",
}


class SupabaseStockAdjustmentRepository(StockAdjustmentRepository):
    def __init__(self, client, company_id, role=None):
        self._client = client
        self._company_id = company_id
        self._role = role
        self._ids = {}

    def adjust_confirmed(self, data: StockAdjustmentInput) -> None:
        product_id = self._product_id(data.product_code)
        if product_id is None:
            raise LookupError(
                f"Produto {data.product_code} não encontrado nesta empresa."
            )

        kind = MovementKind.from_value(data.kind).value

        self._rpc(
            "fn_adjust_product_stock",
            {
                "p_product_id": product_id,
                "p_company_id": self._company_id,
                "p_quantity": int(data.quantity),
                "p_movement_kind": kind,
                "p_justification": data.justification,
            },
        )

    # ======================================================
    # Internos
    # ======================================================

    def _rpc(self, name: str, args: dict):
        try:
            response = self._client.rpc(name, args).execute()
        except Exception as erro:
            if _e_recusa_de_permissao(erro):
                raise PermissionDeniedError(
                    ACTION_BY_RPC.get(name, f"executar {name}"),
                    self._role,
                ) from erro
            raise
        return getattr(response, "data", None)

    def _product_id(self, code: str):
        if code not in self._ids:
            rows = self._client.table("products").select("id").eq(
                "company_id", self._company_id
            ).eq("barcode", code).limit(1).execute()
            linhas = getattr(rows, "data", None) or []
            # Nota: no teste falso, `data` já vem como lista; no cliente real,
            # PostgREST também.
            if linhas:
                self._ids[code] = linhas[0]["id"]
            else:
                self._ids[code] = None
        return self._ids.get(code)
