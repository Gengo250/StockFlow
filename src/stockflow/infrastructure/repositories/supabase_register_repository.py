from uuid import UUID
from supabase import Client
from stockflow.application.ports.register_repository import RegisterRepository
from stockflow.application.dto.register_input import (
    OpenRegisterInput,
    CloseRegisterInput,
)


class SupabaseRegisterRepository(RegisterRepository):
    def __init__(self, supabase: Client):
        self._supabase = supabase

    def open_session(self, input_dto: OpenRegisterInput) -> UUID:
        payload = {
            "p_company_id": str(input_dto.company_id),
            "p_register_id": str(input_dto.register_id),
            "p_operator_id": str(input_dto.operator_id),
            "p_session_id": str(input_dto.session_id) if input_dto.session_id else None,
            "p_initial_balance": float(input_dto.initial_balance),
        }
        response = self._supabase.rpc("fn_open_register_session", payload).execute()
        if not response.data:
            raise RuntimeError("Falha ao abrir a sessão de caixa.")
        return UUID(response.data)

    def close_session(self, input_dto: CloseRegisterInput) -> dict:
        payload = {
            "p_register_log_id": str(input_dto.register_log_id),
            "p_declared_dinheiro": float(input_dto.declared_dinheiro),
            "p_declared_debito": float(input_dto.declared_debito),
            "p_declared_credito": float(input_dto.declared_credito),
            "p_declared_pix": float(input_dto.declared_pix),
            "p_declared_vale": float(input_dto.declared_vale),
            "p_declared_outro": float(input_dto.declared_outro),
            "p_justification": input_dto.justification,
        }
        response = self._supabase.rpc("fn_close_register_session", payload).execute()
        return response.data
