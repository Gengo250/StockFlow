"""Testes unitários da história US24: Registrar eventos imutáveis de auditoria."""

from datetime import datetime, timezone
import pytest

from stockflow.application.dto.audit_input import AuditEventInput
from stockflow.application.services.audit_sanitizer import (
    AuditSanitizer,
    is_sensitive_key,
    sanitize_sensitive_data,
)
from stockflow.application.services.audit_service import AuditService
from stockflow.domain.audit_event import AuditEvent
from stockflow.domain.enums.audit_policy import AuditFailurePolicy
from stockflow.domain.exceptions.audit_errors import (
    AuditImmutabilityError,
    AuditValidationError,
    CriticalAuditFailureError,
)
from stockflow.infrastructure.repositories.demo_audit_repository import DemoAuditRepository


# =====================================================================
# 1. TESTES DO MODELO AuditEvent (Campos obrigatórios e imutabilidade)
# =====================================================================


def test_audit_event_cria_com_campos_obrigatorios():
    ev = AuditEvent(
        user="admin@stockflow.com",
        action="UPDATE_PRICE",
        entity="Product",
        entity_id="PRD-001",
    )
    assert ev.user == "admin@stockflow.com"
    assert ev.action == "UPDATE_PRICE"
    assert ev.entity == "Product"
    assert ev.entity_id == "PRD-001"
    assert ev.occurred_at is not None
    assert ev.occurred_at.tzinfo == timezone.utc
    assert ev.id is not None
    assert not ev.is_critical
    assert ev.old_values is None
    assert ev.new_values is None


def test_audit_event_rejeita_campos_obrigatorios_vazios_ou_ausentes():
    with pytest.raises(AuditValidationError, match="usuário responsável"):
        AuditEvent(user="", action="ACT", entity="ENT", entity_id="1")

    with pytest.raises(AuditValidationError, match="usuário responsável"):
        AuditEvent(user=None, action="ACT", entity="ENT", entity_id="1")

    with pytest.raises(AuditValidationError, match="ação do evento"):
        AuditEvent(user="user", action="", entity="ENT", entity_id="1")

    with pytest.raises(AuditValidationError, match="entidade do evento"):
        AuditEvent(user="user", action="ACT", entity="", entity_id="1")

    with pytest.raises(AuditValidationError, match="identificador da entidade"):
        AuditEvent(user="user", action="ACT", entity="ENT", entity_id="")


def test_audit_event_e_estritamente_imutavel():
    ev = AuditEvent(
        user="admin",
        action="CREATE",
        entity="Product",
        entity_id="P1",
        old_values={"price": 10},
        new_values={"price": 15},
    )

    # Tentativa de alterar atributos do evento
    with pytest.raises(AuditImmutabilityError):
        ev.action = "DELETE"

    with pytest.raises(AuditImmutabilityError):
        ev.user = "hacker"

    # Tentativa de deletar atributos do evento
    with pytest.raises(AuditImmutabilityError):
        del ev.action

    # Tentativa de mutar o dicionário interno (MappingProxy)
    with pytest.raises(TypeError):
        ev.old_values["price"] = 99


# =====================================================================
# 2. TESTES DE SANITIZAÇÃO DE DADOS SECRETOS (Senhas, tokens, etc.)
# =====================================================================


def test_deteccao_de_chaves_sensiveis():
    assert is_sensitive_key("password")
    assert is_sensitive_key("current_password")
    assert is_sensitive_key("SENHA")
    assert is_sensitive_key("user_token")
    assert is_sensitive_key("jwt_secret")
    assert is_sensitive_key("api_key")
    assert is_sensitive_key("privkey")
    assert is_sensitive_key("cvv")
    assert not is_sensitive_key("username")
    assert not is_sensitive_key("product_name")
    assert not is_sensitive_key("price")


def test_sanitizacao_remove_chaves_secretas():
    payload = {
        "user": "joao",
        "password": "super-secret-password-123",
        "token": "bearer-token-abc",
        "api_key": "key-xyz",
        "safe_field": "public_data",
        "nested": {
            "senha_antiga": "123456",
            "name": "João",
            "access_token": "tok123",
        },
    }

    sanitizado = sanitize_sensitive_data(payload)

    # Segredos devem ser removidos
    assert "password" not in sanitizado
    assert "token" not in sanitizado
    assert "api_key" not in sanitizado
    assert "senha_antiga" not in sanitizado["nested"]
    assert "access_token" not in sanitizado["nested"]

    # Dados não sensíveis devem ser preservados
    assert sanitizado["user"] == "joao"
    assert sanitizado["safe_field"] == "public_data"
    assert sanitizado["nested"]["name"] == "João"


def test_sanitizacao_mascara_tokens_em_strings():
    texto = "Tentativa de login com Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"
    sanitizado = sanitize_sensitive_data(texto)
    assert "eyJhbGciOiJIUzI1NiJ9" not in sanitizado
    assert "Bearer [REDACTED]" in sanitizado


# =====================================================================
# 3. TESTES DO SERVIÇO CENTRAL DE AUDITORIA (AuditService)
# =====================================================================


def test_servico_cria_evento_com_sanitizacao_e_preserva_ambos_estados():
    repo = DemoAuditRepository()
    service = AuditService(repo)

    evento = service.record(
        user="gerente@empresa.com",
        action="UPDATE_USER",
        entity="User",
        entity_id="usr-123",
        old_values={"nome": "Carlos", "senha": "antiga_123", "role": "SELLER"},
        new_values={"nome": "Carlos Silva", "senha": "nova_456", "role": "ADMIN"},
        is_critical=True,
    )

    assert evento is not None
    assert evento.user == "gerente@empresa.com"
    assert evento.action == "UPDATE_USER"
    assert evento.entity == "User"
    assert evento.entity_id == "usr-123"
    assert evento.is_critical is True

    # Preserva ambos os estados
    assert evento.old_values["nome"] == "Carlos"
    assert evento.old_values["role"] == "SELLER"
    assert evento.new_values["nome"] == "Carlos Silva"
    assert evento.new_values["role"] == "ADMIN"

    # Segredos removidos
    assert "senha" not in evento.old_values
    assert "senha" not in evento.new_values


def test_servico_aceita_dto_input():
    repo = DemoAuditRepository()
    service = AuditService(repo)

    dto = AuditEventInput(
        user="admin",
        action="DELETE_PRODUCT",
        entity="Product",
        entity_id="PRD-009",
        is_critical=True,
    )
    ev = service.record_event(dto)
    assert ev.action == "DELETE_PRODUCT"
    assert ev.entity_id == "PRD-009"
    assert ev.is_critical is True


def test_servico_extrai_usuario_de_objeto_sessao():
    from types import SimpleNamespace

    repo = DemoAuditRepository()
    service = AuditService(repo)

    sessao = SimpleNamespace(name="Ana Auditora", role="ADMIN", email="ana@auditor.com")
    ev = service.record(
        user=sessao,
        action="LOGIN",
        entity="Session",
        entity_id="sess-01",
    )
    assert ev.user == "Ana Auditora"


def test_servico_rejeita_campos_obrigatorios_ausentes():
    service = AuditService(DemoAuditRepository())

    with pytest.raises(AuditValidationError):
        service.record(user="", action="A", entity="E", entity_id="1")

    with pytest.raises(AuditValidationError):
        service.record(user="u", action="", entity="E", entity_id="1")

    with pytest.raises(AuditValidationError):
        service.record(user="u", action="A", entity="", entity_id="1")

    with pytest.raises(AuditValidationError):
        service.record(user="u", action="A", entity="E", entity_id="")


# =====================================================================
# 4. POLÍTICAS DE TRATAMENTO DE FALHAS (Operações críticas vs comuns)
# =====================================================================


class RepositorioComFalha:
    def record(self, event):
        raise ConnectionError("Banco de dados indisponível")


def test_falha_em_operacao_critica_lanca_critical_audit_failure_error():
    """Política FAIL_ON_CRITICAL: Falhas no registro de operação crítica impedem a operação."""
    service = AuditService(RepositorioComFalha(), policy=AuditFailurePolicy.FAIL_ON_CRITICAL)

    with pytest.raises(CriticalAuditFailureError, match="Falha ao persistir evento de auditoria"):
        service.record(
            user="admin",
            action="ALTERAR_PERMISSAO",
            entity="User",
            entity_id="usr-1",
            is_critical=True,
        )


def test_falha_em_operacao_nao_critica_nao_interrompe():
    """Política FAIL_ON_CRITICAL: Falhas em operações não críticas são absorvidas com log."""
    service = AuditService(RepositorioComFalha(), policy=AuditFailurePolicy.FAIL_ON_CRITICAL)

    resultado = service.record(
        user="seller",
        action="CONSULTAR_CATALOGO",
        entity="Product",
        entity_id="PRD-01",
        is_critical=False,
    )
    assert resultado is None


def test_politica_fail_always_lanca_inclusive_para_nao_critica():
    service = AuditService(RepositorioComFalha(), policy=AuditFailurePolicy.FAIL_ALWAYS)

    with pytest.raises(CriticalAuditFailureError):
        service.record(
            user="seller",
            action="CONSULTAR",
            entity="Product",
            entity_id="PRD-01",
            is_critical=False,
        )


def test_politica_log_only_nao_lanca_mesmo_para_critica():
    service = AuditService(RepositorioComFalha(), policy=AuditFailurePolicy.LOG_ONLY)

    res = service.record(
        user="admin",
        action="EXCLUIR_TUDO",
        entity="System",
        entity_id="sys",
        is_critical=True,
    )
    assert res is None


# =====================================================================
# 5. GARANTIA DE IMUTABILIDADE NA APLICAÇÃO (Vedação de update/delete)
# =====================================================================


def test_servico_impede_edicao_e_exclusao():
    service = AuditService(DemoAuditRepository())

    with pytest.raises(AuditImmutabilityError, match="não podem ser editados"):
        service.update("ev-1", action="NEW")

    with pytest.raises(AuditImmutabilityError, match="não podem ser editados"):
        service.edit("ev-1")

    with pytest.raises(AuditImmutabilityError, match="não podem ser excluídos"):
        service.delete("ev-1")

    with pytest.raises(AuditImmutabilityError, match="não podem ser excluídos"):
        service.remove("ev-1")

    with pytest.raises(AuditImmutabilityError, match="não podem ser excluídos"):
        service.clear()
