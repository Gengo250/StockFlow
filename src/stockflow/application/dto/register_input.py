from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class OpenRegisterInput(BaseModel):
    company_id: UUID
    register_id: UUID
    operator_id: UUID
    session_id: Optional[UUID] = None
    initial_balance: Decimal = Field(
        ..., ge=0, description="Saldo inicial não pode ser negativo"
    )


class CloseRegisterInput(BaseModel):
    register_log_id: UUID
    declared_dinheiro: Decimal = Field(default=Decimal("0.00"), ge=0)
    declared_debito: Decimal = Field(default=Decimal("0.00"), ge=0)
    declared_credito: Decimal = Field(default=Decimal("0.00"), ge=0)
    declared_pix: Decimal = Field(default=Decimal("0.00"), ge=0)
    declared_vale: Decimal = Field(default=Decimal("0.00"), ge=0)
    declared_outro: Decimal = Field(default=Decimal("0.00"), ge=0)
    justification: Optional[str] = None
