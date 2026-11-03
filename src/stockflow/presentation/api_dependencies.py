"""Authentication and dependency construction for the HTTP API."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from stockflow.domain.entities.session import Session
from stockflow.domain.enums.user_role import UserRole
from stockflow.infrastructure.database.api_client import (
    InvalidAccessToken,
    create_authenticated_client,
)
from stockflow.application.services.register_service import RegisterService
from stockflow.infrastructure.repositories.supabase_register_repository import (
    SupabaseRegisterRepository,
)

_bearer = HTTPBearer(auto_error=False)


def get_api_client(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
):
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Autenticação Bearer obrigatória.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return create_authenticated_client(credentials.credentials)
    except InvalidAccessToken:
        raise HTTPException(
            status_code=401,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def get_current_register_operator(
    client=Depends(get_api_client),
    company_id: UUID = Header(..., alias="X-Company-ID"),
) -> Session:
    user_id = client.rpc("fn_current_user_id", {}).execute().data
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuário não autenticado.")

    companies = client.rpc("fn_my_companies", {}).execute().data or []
    selected_company = next(
        (
            company
            for company in companies
            if str(company.get("company_id")) == str(company_id)
        ),
        None,
    )
    if selected_company is None:
        raise HTTPException(
            status_code=403,
            detail="Usuário sem acesso à empresa selecionada.",
        )

    try:
        role = UserRole.from_value(selected_company["user_role"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=403, detail="Papel de usuário inválido.") from None
    if role not in {UserRole.ADMIN, UserRole.SELLER}:
        raise HTTPException(
            status_code=403,
            detail="Apenas administradores ou vendedores podem operar o caixa.",
        )

    return Session(
        user_id=str(user_id),
        name="Operador",
        email="",
        role=role,
        company_id=str(company_id),
    )


def get_register_service(client=Depends(get_api_client)) -> RegisterService:
    return RegisterService(SupabaseRegisterRepository(client))
