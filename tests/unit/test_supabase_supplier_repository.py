"""Contrato do adaptador Supabase para fornecedores."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stockflow.application.dto.supplier_input import SupplierInput
from stockflow.infrastructure.repositories.supabase_supplier_repository import (
    SupabaseSupplierRepository,
)
from test_supabase_product_repository import (
    COMPANY, ClienteFalso, ErroDoPostgrest,
)

SUPPLIER_ID = "77777777-7777-7777-7777-777777777777"


def repository(client):
    return SupabaseSupplierRepository(client, COMPANY, role="ADMIN")


def test_list_and_search_use_company_scoped_rpc():
    rows = [{
        "id": SUPPLIER_ID, "name": "Comercial Sul", "document": "52998224725",
        "phone": "11998877665", "email": "sul@example.com", "address": "Rua A",
        "active": True,
    }]
    client = ClienteFalso(rpc_resultados={"fn_list_company_suppliers": rows})
    repo = repository(client)

    supplier = repo.search("Sul")[0]

    assert supplier.supplier_id == SUPPLIER_ID
    assert supplier.document == "52998224725"
    assert client.chamadas_rpc == [(
        "fn_list_company_suppliers",
        {"p_company_id": COMPANY, "p_search": "Sul"},
    )]


def test_create_uses_rpc_and_maps_returned_database_id():
    client = ClienteFalso(rpc_resultados={"fn_create_supplier": SUPPLIER_ID})
    supplier = repository(client).create(
        SupplierInput(
            name="Comercial Sul", document="52998224725", phone="11998877665",
            email="sul@example.com", address="Rua A",
        )
    )
    assert supplier.supplier_id == SUPPLIER_ID
    assert client.chamadas_rpc == [(
        "fn_create_supplier",
        {
            "p_company_id": COMPANY,
            "p_name": "Comercial Sul",
            "p_document": "52998224725",
            "p_phone": "11998877665",
            "p_email": "sul@example.com",
            "p_address": "Rua A",
        },
    )]


def test_update_and_toggle_use_soft_delete_functions():
    client = ClienteFalso()
    repo = repository(client)
    repo.update(
        SUPPLIER_ID,
        SupplierInput(name="Novo nome", active=True),
    )
    repo.set_active(SUPPLIER_ID, False)

    assert client.chamadas_rpc[0] == (
        "fn_update_supplier",
        {
            "p_supplier_id": SUPPLIER_ID,
            "p_name": "Novo nome",
            "p_document": None,
            "p_phone": "",
            "p_email": "",
            "p_address": "",
            "p_active": True,
        },
    )
    assert client.chamadas_rpc[1] == (
        "fn_set_supplier_active",
        {"p_supplier_id": SUPPLIER_ID, "p_active": False},
    )


def test_permission_denial_is_translated_and_other_errors_propagate():
    client = ClienteFalso(
        rpc_erros={
            "fn_set_supplier_active": ErroDoPostgrest(
                "Sem permissão para alterar fornecedor", code="42501"
            )
        }
    )
    try:
        repository(client).set_active(SUPPLIER_ID, False)
    except Exception as error:
        assert "alterar status de fornecedores" in str(error)
    else:
        raise AssertionError("A recusa de permissão deveria ser traduzida.")

    other = ErroDoPostgrest("database unavailable", code="08006")
    client = ClienteFalso(rpc_erros={"fn_create_supplier": other})
    try:
        repository(client).create(SupplierInput(name="Teste"))
    except ErroDoPostgrest as error:
        assert error is other
    else:
        raise AssertionError("Erro inesperado deveria ser propagado.")
