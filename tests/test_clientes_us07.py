import pytest

from stockflow.application.dto.client_input import ClientInput
from stockflow.application.services.client_service import ClientService
from stockflow.infrastructure.repositories.demo_client_repository import DemoClientRepository


@pytest.fixture
def service():
    return ClientService(DemoClientRepository())


def test_criacao_e_inativacao_de_cliente(service):
    cliente = service.create_client(
        ClientInput(name="Maria Souza", email="maria@example.com", phone="11999887766", document="529.982.247-25")
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
            document="111.444.777-35",
            active=True,
        ),
    )
    assert atualizado.email == "joao.novo@example.com"
    assert atualizado.phone == "11987654321"
    assert atualizado.document == "11144477735"


@pytest.mark.parametrize(
    "document",
    ["529.982.247-25", "11.222.333/0001-81"],
)
def test_accepts_valid_cpf_and_cnpj(service, document):
    client = service.create_client(ClientInput(name="Documento válido", document=document))
    assert client.document == "".join(char for char in document if char.isdigit())


@pytest.mark.parametrize(
    "document",
    [
        "12345678900",
        "52998224724",
        "11222333000180",
        "11111111111",
        "123",
        "529a98224725",
    ],
)
def test_rejects_invalid_or_bad_checksum_documents(service, document):
    with pytest.raises(ValueError, match="CPF/CNPJ"):
        service.create_client(ClientInput(name="Documento inválido", document=document))


def test_allows_client_without_document(service):
    client = service.create_client(ClientInput(name="Sem documento"))
    assert client.document == ""


def test_rejects_duplicate_document_even_when_existing_client_is_inactive(service):
    existing = service.create_client(
        ClientInput(name="Cliente antigo", document="52998224725")
    )
    service.set_active(existing.client_id, False)
    with pytest.raises(ValueError, match="Já existe"):
        service.create_client(
            ClientInput(name="Cliente duplicado", document="529.982.247-25")
        )


def test_update_does_not_treat_same_clients_document_as_duplicate(service):
    client = service.create_client(
        ClientInput(name="Cliente atual", document="52998224725")
    )
    updated = service.update_client(
        client.client_id,
        ClientInput(name="Cliente atualizada", document="529.982.247-25"),
    )
    assert updated.name == "Cliente atualizada"
    assert updated.document == "52998224725"


def test_update_rejects_document_used_by_another_client(service):
    service.create_client(ClientInput(name="Primeiro", document="52998224725"))
    second = service.create_client(ClientInput(name="Segundo"))
    with pytest.raises(ValueError, match="Já existe"):
        service.update_client(
            second.client_id,
            ClientInput(name="Segundo", document="52998224725"),
        )


def test_search_matches_name_document_phone_and_email(service):
    client = service.create_client(
        ClientInput(
            name="Marina Costa",
            document="529.982.247-25",
            phone="(11) 99887-7665",
            email="marina@example.com",
        )
    )
    for query in ("Marina", "529982247", "998877665", "MARINA@EXAMPLE"):
        assert [match.client_id for match in service.search_clients(query)] == [
            client.client_id
        ]


def test_search_without_match_returns_empty_result(service):
    assert service.search_clients("não existe") == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "endereco-inválido"},
        {"email": "sem.dominio@exemplo"},
        {"phone": "1234"},
        {"phone": "abc11999887766"},
    ],
)
def test_rejects_invalid_optional_contact_data(service, overrides):
    with pytest.raises(ValueError):
        service.create_client(ClientInput(name="Contato inválido", **overrides))
