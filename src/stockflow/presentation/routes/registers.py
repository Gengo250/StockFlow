"""HTTP endpoints for opening and closing register sessions."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from stockflow.application.dto.register_input import (
    CloseRegisterInput,
    OpenRegisterInput,
)
from stockflow.application.services.register_service import RegisterService
from stockflow.domain.entities.session import Session
from stockflow.presentation.api_dependencies import (
    get_current_register_operator,
    get_register_service,
)

router = APIRouter(prefix="/registers", tags=["registers"])


class OpenRegisterRequest(BaseModel):
    register_id: UUID
    initial_balance: Decimal = Field(ge=0)


class CloseRegisterRequest(BaseModel):
    declared_dinheiro: Decimal = Field(default=Decimal("0.00"), ge=0)
    declared_debito: Decimal = Field(default=Decimal("0.00"), ge=0)
    declared_credito: Decimal = Field(default=Decimal("0.00"), ge=0)
    declared_pix: Decimal = Field(default=Decimal("0.00"), ge=0)
    declared_vale: Decimal = Field(default=Decimal("0.00"), ge=0)
    declared_outro: Decimal = Field(default=Decimal("0.00"), ge=0)
    justification: str | None = None


@router.post("/open", status_code=status.HTTP_201_CREATED)
def open_register_session(
    payload: OpenRegisterRequest,
    session: Session = Depends(get_current_register_operator),
    service: RegisterService = Depends(get_register_service),
):
    data = OpenRegisterInput(
        company_id=UUID(session.company_id),
        register_id=payload.register_id,
        operator_id=UUID(session.user_id),
        initial_balance=payload.initial_balance,
    )
    register_log_id = service.open_register(data)
    return {"status": "OPEN", "register_log_id": str(register_log_id)}


@router.post("/{register_log_id}/close")
def close_register_session(
    register_log_id: UUID,
    payload: CloseRegisterRequest,
    session: Session = Depends(get_current_register_operator),
    service: RegisterService = Depends(get_register_service),
):
    result = service.close_register(
        CloseRegisterInput(register_log_id=register_log_id, **payload.model_dump())
    )
    return result
