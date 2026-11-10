from uuid import UUID
from stockflow.application.ports.register_repository import RegisterRepository
from stockflow.application.dto.register_input import (
    OpenRegisterInput,
    CloseRegisterInput,
)


class RegisterService:
    def __init__(self, repository: RegisterRepository):
        self._repository = repository

    def open_register(self, data: OpenRegisterInput) -> UUID:
        return self._repository.open_session(data)

    def close_register(self, data: CloseRegisterInput) -> dict:
        return self._repository.close_session(data)

    def register_summary(self, register_log_id: UUID) -> dict:
        return self._repository.get_summary(register_log_id)
