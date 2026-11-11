"""Testes unitários da história US25: consulta paginada de auditoria, filtros e controle de acesso."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import pytest

from stockflow.application.dto.audit_filter import (
    AuditFilter,
    AuditPage,
    ORDENACOES_AUDITORIA,
    TAMANHO_MAXIMO_AUDITORIA,
    TAMANHO_PADRAO_AUDITORIA,
)
from stockflow.application.services.price_history_service import PriceHistoryService
from stockflow.domain.entities.session import Session
from stockflow.domain.enums.price_edit_field import PriceEditField
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.price_change import PriceChange
from stockflow.infrastructure.repositories.demo_price_history_repository import (
    DemoPriceHistoryRepository,
)
from stockflow.infrastructure.repositories.supabase_price_history_repository import (
    SupabasePriceHistoryRepository,
)

COMPANY_ID = "c0000000-0000-0000-0000-000000000001"
PRODUTO_ID = "p0000000-0000-0000-0000-000000000001"


def sessao(papel: UserRole | None) -> Session | None:
    if papel is None:
        return None
    return Session("u-1", "Auditor Teste", "auditor@test.com", papel, COMPANY_ID)


class RepositorioAuditoriaFalso:
    def __init__(self, rows=(), total=0):
        self.rows = tuple(rows)
        self.total = total or len(rows)
        self.chamadas = []

    def list_price_edits(self, product_code=None):
        return self.rows

    def list_audit_page(self, filtro, page, size):
        self.chamadas.append((filtro, page, size))
        inicio = (page - 1) * size
        return AuditPage(
            rows=self.rows[inicio : inicio + size],
            total=self.total,
            page=page,
            size=size,
        )


def evento(day=6, user="Ana", field=PriceEditField.SELL_PRICE, code="PRD-001", **extra):
    return PriceChange(
        changed_on=datetime(2026, 11, day, 10, tzinfo=timezone.utc),
        product_code=code,
        product_name="Produto Teste",
        field=field,
        old_price=Decimal("100.00"),
        new_price=Decimal("120.00"),
        changed_by=user,
        **extra,
    )


# =====================================================================
# 1. TESTES DO DTO AuditFilter e AuditPage
# =====================================================================


def test_filtro_padrao_e_inativo():
    f = AuditFilter()
    assert f.sort == "DATA_DESC"
    assert not f.ativo
    assert f.user is None
    assert f.date_from is None
    assert f.date_to is None
    assert f.action is None
    assert f.entity is None
    assert f.product_code is None


def test_filtro_ativo_com_qualquer_campo():
    assert AuditFilter(user="Ana").ativo
    assert AuditFilter(date_from=date(2026, 11, 1)).ativo
    assert AuditFilter(date_to=date(2026, 11, 2)).ativo
    assert AuditFilter(action=PriceEditField.SELL_PRICE).ativo
    assert AuditFilter(entity="produto").ativo
    assert AuditFilter(product_code="PRD-001").ativo


def test_filtro_recusa_ordenacao_desconhecida():
    with pytest.raises(ValueError, match="Ordenação desconhecida"):
        AuditFilter(sort="INVALIDO")


def test_filtro_recusa_data_inicial_posterior_a_final():
    with pytest.raises(ValueError, match="A data inicial não pode ser depois da final"):
        AuditFilter(date_from=date(2026, 11, 10), date_to=date(2026, 11, 5))


def test_filtro_com_substitui_campos():
    f1 = AuditFilter(user="Ana")
    f2 = f1.com(user="Bia", product_code="PRD-002")
    assert f1.user == "Ana"
    assert f2.user == "Bia"
    assert f2.product_code == "PRD-002"


def test_audit_page_calculo_de_paginas():
    p1 = AuditPage(rows=(), total=120, page=1, size=50)
    assert p1.pages == 3
    assert p1.has_next
    assert not p1.has_previous

    p2 = AuditPage(rows=(), total=120, page=2, size=50)
    assert p2.has_next
    assert p2.has_previous

    p3 = AuditPage(rows=(), total=120, page=3, size=50)
    assert not p3.has_next
    assert p3.has_previous

    vazia = AuditPage(rows=(), total=0, page=1, size=50)
    assert vazia.pages == 1
    assert not vazia.has_next
    assert not vazia.has_previous


# =====================================================================
# 2. CONTROLE DE ACESSO E VALIDAÇÕES DO SERVIÇO
# =====================================================================


def test_apenas_admin_pode_consultar_auditoria():
    repo = RepositorioAuditoriaFalso(rows=[evento()])
    svc = PriceHistoryService(repo)

    # ADMIN: permitido
    res = svc.list_audit_page(sessao(UserRole.ADMIN))
    assert len(res.rows) == 1

    # STOCK, SELLER e anônimo: recusado com PermissionDeniedError
    with pytest.raises(PermissionDeniedError):
        svc.list_audit_page(sessao(UserRole.STOCK))

    with pytest.raises(PermissionDeniedError):
        svc.list_audit_page(sessao(UserRole.SELLER))

    with pytest.raises(PermissionDeniedError):
        svc.list_audit_page(None)


def test_list_page_alias_de_list_audit_page():
    repo = RepositorioAuditoriaFalso(rows=[evento()])
    svc = PriceHistoryService(repo)
    res = svc.list_page(sessao(UserRole.ADMIN))
    assert len(res.rows) == 1


def test_servico_valida_pagina_e_tamanho():
    repo = RepositorioAuditoriaFalso()
    svc = PriceHistoryService(repo)
    s = sessao(UserRole.ADMIN)

    with pytest.raises(ValueError, match="Página inválida"):
        svc.list_audit_page(s, page=0)

    with pytest.raises(ValueError, match="Página inválida"):
        svc.list_audit_page(s, page=-1)

    with pytest.raises(ValueError, match="Página inválida"):
        svc.list_audit_page(s, page="1")  # tipo incorreto

    with pytest.raises(ValueError, match="Tamanho de página inválido"):
        svc.list_audit_page(s, size=0)

    with pytest.raises(ValueError, match="Tamanho de página inválido"):
        svc.list_audit_page(s, size=201)


def test_auditoria_e_estritamente_somente_leitura():
    """Garante que o serviço e porta não expõem métodos de edição ou exclusão."""
    svc = PriceHistoryService(RepositorioAuditoriaFalso())
    for verbo in ("edit", "update", "delete", "remove", "cancel", "revert"):
        assert not hasattr(svc, verbo)
        assert not hasattr(svc, f"{verbo}_event")
        assert not hasattr(svc, f"{verbo}_audit")


# =====================================================================
# 3. REPOSITÓRIO DEMO (FILTROS, ORDENAÇÃO E PAGINAÇÃO)
# =====================================================================


class CatalogoFalso:
    def __init__(self, produtos):
        self._produtos = produtos

    def get(self, codigo):
        return self._produtos.get(codigo)


@pytest.fixture
def repo_demo():
    agora = datetime(2026, 11, 10, 12, 0, 0)
    semente = (
        (1, "PRD-001", PriceEditField.SELL_PRICE, "100.00", "120.00", "Ana Ferreira"),
        (2, "PRD-001", PriceEditField.BUY_PRICE, "70.00", "80.00", "Carlos Auditor"),
        (3, "PRD-002", PriceEditField.SELL_PRICE, "200.00", "220.00", "Ana Ferreira"),
        (4, "PRD-002", PriceEditField.BUY_PRICE, "150.00", "160.00", "Bia Estoquista"),
        (5, "PRD-003", PriceEditField.SELL_PRICE, "50.00", "55.00", "Carlos Auditor"),
    )
    catalogo = CatalogoFalso({
        "PRD-001": SimpleNamespace(code="PRD-001", name="Teclado"),
        "PRD-002": SimpleNamespace(code="PRD-002", name="Mouse"),
        "PRD-003": SimpleNamespace(code="PRD-003", name="Monitor"),
    })
    return DemoPriceHistoryRepository(catalogo, seed=semente, agora=agora)


def test_demo_paginacao_e_tamanho(repo_demo):
    p1 = repo_demo.list_audit_page(page=1, size=2)
    assert len(p1.rows) == 2
    assert p1.total == 5
    assert p1.pages == 3
    assert p1.has_next
    assert not p1.has_previous

    p2 = repo_demo.list_audit_page(page=2, size=2)
    assert len(p2.rows) == 2
    assert p2.rows[0].product_code == "PRD-002"

    p3 = repo_demo.list_audit_page(page=3, size=2)
    assert len(p3.rows) == 1
    assert not p3.has_next


def test_demo_filtro_por_usuario(repo_demo):
    f = AuditFilter(user="Ana")
    pagina = repo_demo.list_audit_page(filtro=f)
    assert pagina.total == 2
    assert all("Ana" in r.changed_by for r in pagina.rows)


def test_demo_filtro_por_acao(repo_demo):
    f = AuditFilter(action=PriceEditField.BUY_PRICE)
    pagina = repo_demo.list_audit_page(filtro=f)
    assert pagina.total == 2
    assert all(r.field == PriceEditField.BUY_PRICE for r in pagina.rows)


def test_demo_filtro_por_entidade(repo_demo):
    f_ok = AuditFilter(entity="produto")
    assert repo_demo.list_audit_page(filtro=f_ok).total == 5

    f_outro = AuditFilter(entity="cliente")
    assert repo_demo.list_audit_page(filtro=f_outro).total == 0


def test_demo_filtro_por_periodo(repo_demo):
    # semente tem dias 1, 2, 3, 4, 5 atrás a partir de 10/11/2026:
    # 09/11, 08/11, 07/11, 06/11, 05/11
    f = AuditFilter(date_from=date(2026, 11, 7), date_to=date(2026, 11, 9))
    pagina = repo_demo.list_audit_page(filtro=f)
    assert pagina.total == 3
    for r in pagina.rows:
        assert date(2026, 11, 7) <= r.changed_on.date() <= date(2026, 11, 9)


def test_demo_combinacao_de_filtros(repo_demo):
    f = AuditFilter(
        user="Ana",
        action=PriceEditField.SELL_PRICE,
        entity="produto",
        product_code="PRD-001",
        date_from=date(2026, 11, 8),
        date_to=date(2026, 11, 10),
    )
    pagina = repo_demo.list_audit_page(filtro=f)
    assert pagina.total == 1
    assert pagina.rows[0].product_code == "PRD-001"
    assert pagina.rows[0].changed_by == "Ana Ferreira"
    assert pagina.rows[0].field == PriceEditField.SELL_PRICE


def test_demo_ordenacao_mais_recentes_primeiro(repo_demo):
    pagina = repo_demo.list_audit_page(filtro=AuditFilter(sort="DATA_DESC"))
    datas = [r.changed_on for r in pagina.rows]
    assert datas == sorted(datas, reverse=True)


def test_demo_ordenacao_mais_antigas_primeiro(repo_demo):
    pagina = repo_demo.list_audit_page(filtro=AuditFilter(sort="DATA_ASC"))
    datas = [r.changed_on for r in pagina.rows]
    assert datas == sorted(datas)


# =====================================================================
# 4. REPOSITÓRIO SUPABASE (CONTRATO RPC E MAPPEAMENTO)
# =====================================================================


class ClientRpcMock:
    def __init__(self, retorno_rpc=None, retorno_table=None):
        self.retorno_rpc = retorno_rpc or []
        self.retorno_table = retorno_table or []
        self.chamadas_rpc = []

    def rpc(self, nome, args):
        self.chamadas_rpc.append((nome, args))
        mock = SimpleNamespace()
        mock.execute = lambda: SimpleNamespace(data=self.retorno_rpc)
        return mock

    def table(self, _nome):
        builder = SimpleNamespace()
        builder.select = lambda *_: builder
        builder.eq = lambda *_: builder
        builder.limit = lambda *_: builder
        builder.execute = lambda: SimpleNamespace(data=self.retorno_table)
        return builder


def test_supabase_chama_rpc_com_filtros_e_paginacao():
    dados_mock = [
        {
            "id": "e0000000-0000-0000-0000-000000000001",
            "changed_on": "2026-11-06T15:00:00+00:00",
            "product_id": PRODUTO_ID,
            "product_code": "PRD-001",
            "product_name": "Teclado",
            "field": "SELL_PRICE",
            "old_price": "100.00",
            "new_price": "120.00",
            "changed_by": "Ana",
            "entity": "Produto",
            "total_count": 1,
        }
    ]
    client = ClientRpcMock(
        retorno_rpc=dados_mock,
        retorno_table=[{"id": PRODUTO_ID}],
    )
    repo = SupabasePriceHistoryRepository(client, COMPANY_ID)
    filtro = AuditFilter(
        user="Ana",
        action=PriceEditField.SELL_PRICE,
        entity="produto",
        product_code="PRD-001",
        date_from=date(2026, 11, 6),
        date_to=date(2026, 11, 6),
        sort="DATA_DESC",
    )

    page = repo.list_audit_page(filtro, page=1, size=20)

    assert len(client.chamadas_rpc) == 1
    nome_rpc, args = client.chamadas_rpc[0]
    assert nome_rpc == "fn_list_audit_events"
    assert args["p_company_id"] == COMPANY_ID
    assert args["p_product_id"] == PRODUTO_ID
    assert args["p_user_name"] == "Ana"
    assert args["p_action"] == "SELL_PRICE"
    assert args["p_entity"] == "produto"
    assert args["p_from"] == "2026-11-06"
    assert args["p_to"] == "2026-11-07"  # Inclusivo na tela virou exclusivo no banco (+1 dia)
    assert args["p_sort"] == "DATA_DESC"
    assert args["p_limit"] == 20
    assert args["p_offset"] == 0

    assert page.total == 1
    assert len(page.rows) == 1
    assert page.rows[0].product_code == "PRD-001"
    assert page.rows[0].new_price == Decimal("120.00")


def test_supabase_produto_inexistente_retorna_pagina_vazia():
    client = ClientRpcMock(retorno_rpc=[], retorno_table=[])
    repo = SupabasePriceHistoryRepository(client, COMPANY_ID)
    filtro = AuditFilter(product_code="CODIGO_QUE_NAO_EXISTE")

    page = repo.list_audit_page(filtro, page=1, size=50)
    assert page.total == 0
    assert page.rows == ()
    assert len(client.chamadas_rpc) == 0  # Nem chamou o RPC desnecessariamente
