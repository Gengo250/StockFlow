"""RPCs de caixa: a identidade do operador é resolvida no banco."""
from stockflow.application.dto.register_input import CloseRegisterInput
from stockflow.infrastructure.repositories.supabase_register_repository import SupabaseRegisterRepository


class SupabaseCashRegisterRepository:
    def __init__(self, client, company_id):
        self.client = client
        self.company_id = str(company_id)

    def current(self):
        return self.client.rpc('fn_current_register_session', {
            'p_company_id': self.company_id,
        }).execute().data

    def open(self, balance):
        return self.client.rpc('fn_start_my_register', {
            'p_company_id': self.company_id,
            'p_initial_balance': float(balance),
        }).execute().data

    def _resolve_log_id(self, register_log_id):
        if register_log_id is None:
            current = self.current()
            if not current:
                raise ValueError('Não há caixa aberto.')
            register_log_id = current['id']
        return register_log_id

    def summary(self, *, register_log_id=None):
        return SupabaseRegisterRepository(self.client).get_summary(self._resolve_log_id(register_log_id))

    def close(self, declared, justification, *, register_log_id=None):
        register_log_id = self._resolve_log_id(register_log_id)
        data = CloseRegisterInput(
            register_log_id=register_log_id, justification=justification,
            # Chaves do enum (DINHEIRO, ...) viram os campos declared_* do DTO.
            **{f'declared_{key.lower()}': value for key, value in declared.items()},
        )
        return SupabaseRegisterRepository(self.client).close_session(data)
