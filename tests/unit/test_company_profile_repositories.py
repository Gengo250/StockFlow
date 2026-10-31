"""Dados da empresa emitente (US19/SCRUM-225).

Nada no aplicativo lia `company` antes desta história: a `Session` carrega
só `company_id`. A policy `company_select` e o GRANT já existem desde
`20261003120100_policies_security.sql`, então a leitura é direta e sem
migration.
"""

import pytest

from stockflow.domain.sale_receipt import ReceiptCompany
from stockflow.infrastructure.repositories.demo_company_repository import (
    DemoCompanyRepository,
)
from stockflow.infrastructure.repositories.supabase_company_repository import (
    SupabaseCompanyRepository,
)


class _Resposta:
    def __init__(self, data):
        self.data = data


class _Consulta:
    """Imita `table(...).select(...).eq(...).limit(...).execute()`.

    Guarda o que foi encadeado para que o teste afirme o escopo de empresa:
    um adaptador que esquecesse o `.eq` traria as demais empresas do usuário
    e só falharia em produção.
    """

    def __init__(self, data, registro):
        self._data, self._registro = data, registro

    def select(self, colunas):
        self._registro["select"] = colunas
        return self

    def eq(self, coluna, valor):
        self._registro.setdefault("eq", []).append((coluna, valor))
        return self

    def limit(self, quantidade):
        self._registro["limit"] = quantidade
        return self

    def execute(self):
        if isinstance(self._data, Exception):
            raise self._data
        return _Resposta(self._data)


class _ClienteFalso:
    def __init__(self, data):
        self._data, self.chamadas = data, {}

    def table(self, nome):
        self.chamadas["table"] = nome
        return _Consulta(self._data, self.chamadas)


class _Erro(Exception):
    code = "42501"


def test_demo_devolve_a_empresa_da_demonstracao():
    empresa = DemoCompanyRepository().get_profile()
    assert isinstance(empresa, ReceiptCompany)
    assert empresa.identificada


def test_supabase_le_nome_e_cnpj_escopados_pela_empresa_da_sessao():
    cliente = _ClienteFalso([
        {"id": "c-1", "name": "StockFlow Comércio LTDA", "cnpj": "11222333000181"}
    ])
    empresa = SupabaseCompanyRepository(cliente, "c-1").get_profile()

    assert cliente.chamadas["table"] == "company"
    assert cliente.chamadas["select"] == "id,name,cnpj"
    assert ("id", "c-1") in cliente.chamadas["eq"]
    assert empresa == ReceiptCompany(
        name="StockFlow Comércio LTDA", document="11222333000181"
    )


def test_empresa_sem_cnpj_cadastrado_nao_vira_a_string_none():
    cliente = _ClienteFalso([{"id": "c-1", "name": "Mercearia", "cnpj": None}])
    assert SupabaseCompanyRepository(cliente, "c-1").get_profile().document == ""


def test_leitura_recusada_degrada_em_empresa_vazia_sem_derrubar_a_emissao():
    """O comprovante vale sem o cabeçalho; falhar a emissão por causa dele
    seria perder o documento inteiro por um bloco."""
    empresa = SupabaseCompanyRepository(_ClienteFalso(_Erro()), "c-1").get_profile()
    assert not empresa.identificada


def test_empresa_inexistente_tambem_degrada():
    empresa = SupabaseCompanyRepository(_ClienteFalso([]), "c-1").get_profile()
    assert not empresa.identificada


def test_backend_escolhe_o_adaptador_pela_variavel_de_ambiente(monkeypatch):
    from stockflow.presentation import backend

    monkeypatch.delenv("STOCKFLOW_BACKEND", raising=False)
    assert isinstance(backend.build_company_repository(None), DemoCompanyRepository)


def test_backend_exige_empresa_na_sessao_no_modo_banco(monkeypatch):
    from stockflow.presentation import backend

    monkeypatch.setenv("STOCKFLOW_BACKEND", "supabase")
    with pytest.raises(RuntimeError):
        backend.build_company_repository(object())
