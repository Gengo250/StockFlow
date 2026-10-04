import pytest

from stockflow.application.dto.client_input import ClientInput
from stockflow.application.services.client_service import ClientService
from stockflow.infrastructure.repositories.demo_client_repository import DemoClientRepository


@pytest.fixture
def service():
    return ClientService(DemoClientRepository())


def test_criacao_e_inativacao_de_cliente(service):
    cliente = service.create_client(
        ClientInput(name="Maria Souza", email="maria@example.com", phone="11999887766", document="12345678909")
    )
    assert cliente.name == "Maria Souza"
    assert cliente.active is True

    atualizado = service.set_active(cliente.client_id, False)
    assert atualizado.active is False
    assert atualizado.status == "Inativo"


def test_validacao_exige_nome_do_cliente(service):
    with pytest.raises(ValueError, match="Nome do cliente é obrigatório"):
        service.create_client(ClientInput(name="   "))


def test_pode_atualizar_dados_opcionais(service):
    cliente = service.create_client(ClientInput(name="João Silva", email="joao@example.com"))
    atualizado = service.update_client(
        cliente.client_id,
        ClientInput(
            client_id=cliente.client_id,
            name="João Silva",
            email="joao.novo@example.com",
            phone="11987654321",
            document="11144477735",
            active=True,
        ),
    )
    assert atualizado.email == "joao.novo@example.com"
    assert atualizado.phone == "11987654321"
    assert atualizado.document == "11144477735"
