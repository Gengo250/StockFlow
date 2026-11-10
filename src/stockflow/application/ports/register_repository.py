from abc import ABC, abstractmethod
from uuid import UUID
from stockflow.application.dto.register_input import (
    OpenRegisterInput,
    CloseRegisterInput,
)


class RegisterRepository(ABC):
    @abstractmethod
    def open_session(self, input_dto: OpenRegisterInput) -> UUID:
        pass

    @abstractmethod
    def close_session(self, input_dto: CloseRegisterInput) -> dict:
        pass

    @abstractmethod
    def get_summary(self, register_log_id: UUID) -> dict:
        """Totais por forma de pagamento e total dos totais da sessão."""
        pass
