from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from stockflow.application.services.register_service import RegisterService
from stockflow.domain.entities.session import Session
from stockflow.domain.enums.user_role import UserRole
from stockflow.infrastructure.database.api_client import InvalidAccessToken
from stockflow.presentation import api_dependencies
from stockflow.presentation.api import app
from stockflow.presentation.api_dependencies import (
    get_current_register_operator,
    get_register_service,
)


class FakeSupabase:
    def __init__(self, *, user_id, companies):
        self.user_id = str(user_id)
        self.companies = companies
        self.auth = SimpleNamespace()

    def rpc(self, name, _payload):
        data = {
            "fn_current_user_id": self.user_id,
            "fn_my_companies": self.companies,
        }[name]
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_register_api_requires_bearer_token(client):
    response = client.post(
        "/api/v1/registers/open",
        json={"register_id": str(uuid4()), "initial_balance": "10.00"},
    )

    assert response.status_code == 401


def test_register_api_rejects_invalid_access_token(client, monkeypatch):
    def reject_token(_token):
        raise InvalidAccessToken

    monkeypatch.setattr(
        api_dependencies, "create_authenticated_client", reject_token
    )
    response = client.post(
        "/api/v1/registers/open",
        headers={"Authorization": "Bearer expired"},
        json={"register_id": str(uuid4()), "initial_balance": "10.00"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (UserRole.ADMIN, 201),
        (UserRole.SELLER, 201),
        (UserRole.STOCK, 403),
    ],
)
def test_register_api_allows_admin_and_seller_membership(
    client, monkeypatch, role, expected_status
):
    company_id, user_id = uuid4(), uuid4()
    supabase = FakeSupabase(
        user_id=user_id,
        companies=[{"company_id": str(company_id), "user_role": role.value}],
    )
    monkeypatch.setattr(
        api_dependencies, "create_authenticated_client", lambda _token: supabase
    )
    service = Mock(spec=RegisterService)
    service.open_register.return_value = uuid4()
    app.dependency_overrides[get_register_service] = lambda: service

    response = client.post(
        "/api/v1/registers/open",
        headers={
            "Authorization": "Bearer valid",
            "X-Company-ID": str(company_id),
        },
        json={"register_id": str(uuid4()), "initial_balance": "10.00"},
    )

    assert response.status_code == expected_status
    assert service.open_register.called is (role in {UserRole.ADMIN, UserRole.SELLER})


def test_open_register_uses_authenticated_company_and_operator(client):
    company_id, user_id, register_id, log_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    session = Session(
        user_id=str(user_id),
        name="Admin",
        email="admin@example.com",
        role=UserRole.ADMIN,
        company_id=str(company_id),
    )
    service = Mock(spec=RegisterService)
    service.open_register.return_value = log_id
    app.dependency_overrides[get_current_register_operator] = lambda: session
    app.dependency_overrides[get_register_service] = lambda: service

    response = client.post(
        "/api/v1/registers/open",
        json={
            "register_id": str(register_id),
            "initial_balance": "25.50",
            "company_id": str(uuid4()),
            "operator_id": str(uuid4()),
        },
    )

    assert response.status_code == 201
    assert response.json() == {"status": "OPEN", "register_log_id": str(log_id)}
    data = service.open_register.call_args.args[0]
    assert data.company_id == company_id
    assert data.operator_id == user_id
    assert data.register_id == register_id
    assert data.initial_balance == Decimal("25.50")


def test_close_register_passes_validated_register_payload(client):
    company_id, user_id, log_id = uuid4(), uuid4(), uuid4()
    session = Session(
        user_id=str(user_id),
        name="Admin",
        email="admin@example.com",
        role=UserRole.ADMIN,
        company_id=str(company_id),
    )
    service = Mock(spec=RegisterService)
    service.close_register.return_value = {"status": "CLOSED"}
    app.dependency_overrides[get_current_register_operator] = lambda: session
    app.dependency_overrides[get_register_service] = lambda: service

    response = client.post(
        f"/api/v1/registers/{log_id}/close",
        json={
            "declared_dinheiro": "20.00",
            "justification": "Conferido",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "CLOSED"}
    data = service.close_register.call_args.args[0]
    assert data.register_log_id == log_id
    assert data.declared_dinheiro == Decimal("20.00")
    assert data.justification == "Conferido"


def test_register_api_rejects_company_without_membership(client, monkeypatch):
    company_id = uuid4()
    supabase = FakeSupabase(
        user_id=uuid4(),
        companies=[{"company_id": str(uuid4()), "user_role": "ADMIN"}],
    )
    monkeypatch.setattr(
        api_dependencies, "create_authenticated_client", lambda _token: supabase
    )

    response = client.post(
        "/api/v1/registers/open",
        headers={
            "Authorization": "Bearer valid",
            "X-Company-ID": str(company_id),
        },
        json={"register_id": str(uuid4()), "initial_balance": "10.00"},
    )

    assert response.status_code == 403


def test_register_migration_enforces_register_operator_and_company_scoped_sales():
    migration = (
        Path(__file__).resolve().parents[1]
        / "database"
        / "supabase"
        / "migrations"
        / "20261101170000_us23_register_api_authorization.sql"
    ).read_text(encoding="utf-8")

    assert "ARRAY['ADMIN', 'SELLER']::public.user_role[]" in migration
    assert "v_log.operator_id IS DISTINCT FROM v_actor" in migration
    assert "p_operator_id IS DISTINCT FROM v_actor" in migration
    assert "WHERE company_id = NEW.company_id" in migration
    assert "Há mais de um caixa aberto" in migration
