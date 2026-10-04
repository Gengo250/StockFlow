"""Gravar precisa aparecer na tela, e mexer na tela precisa gravar.

Dois bugs simétricos viveram escondidos porque nenhum teste comparava o
comportamento dos DOIS adaptadores:

1. **Gravava e não aparecia.** `DemoProductRepository` escreve no MESMO dict
   que as telas leem — é essa identidade que faz a tabela refletir. O
   adaptador de banco não tinha esse dict: gravava no Supabase e a foto local
   ficava com o valor antigo até reiniciar a aplicação.

2. **Aparecia e não gravava.** `toggle_product_status` nunca chamava o
   repositório. `set_active` existia no adaptador de banco, estava testado, e
   não tinha um único chamador em `src/` — desativar pela tabela de Estoque
   mudava a tela e não persistia nada.

No modo demonstração os dois caminhos funcionavam por acidente da identidade
do dict, e é exatamente por isso que a suíte inteira passava.
"""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "unit"))

from stockflow.application.dto.product_input import ProductInput
from stockflow.application.services.product_service import ProductService
from stockflow.domain.enums.user_role import UserRole
from stockflow.infrastructure.repositories.supabase_product_repository import (
    SupabaseProductRepository,
)
from stockflow.presentation import backend
from stockflow.presentation.demo_accounts import conta_admin, conta_por_papel
from stockflow.presentation.windows.main_window import MainWindow
from stockflow.presentation.workers import executar_agora

from test_supabase_product_repository import COMPANY, ClienteFalso, catalogo_falso


def dados(**overrides):
    base = dict(
        code="PRD-009", name='Monitor LG UltraWide 34"', category="Eletrônicos",
        unit="Unidade (UN)", sale_price="R$ 2.499,90", cost="R$ 1.850,00",
        stock="3", active=True, minimum_stock=10,
    )
    base.update(overrides)
    return ProductInput(**base)


# ============================================ 1. gravar aparece na tela


def test_gravar_no_banco_reflete_na_foto_que_as_telas_leem():
    """O bug: o saldo ia para o banco e a tela continuava mostrando o antigo."""
    repo = SupabaseProductRepository(ClienteFalso(catalogo_falso()), COMPANY)
    catalogo = repo.load_catalog()          # a foto que a MainWindow guardaria
    assert catalogo["PRD-009"].stock == "18"

    ProductService(repo).update_product(conta_admin().session(), "PRD-009",
                                        dados(stock="3"))

    assert catalogo["PRD-009"].stock == "3"
    assert catalogo["PRD-009"].stock_status == "Baixo"   # 3 contra mínimo 10


def test_cadastrar_tambem_entra_na_foto():
    repo = SupabaseProductRepository(
        ClienteFalso(catalogo_falso(), rpc_resultados={"fn_create_products": "novo-id"}),
        COMPANY,
    )
    catalogo = repo.load_catalog()
    assert "PRD-777" not in catalogo

    ProductService(repo).create_product(
        conta_admin().session(), dados(code="PRD-777", name="Produto Novo"))

    assert catalogo["PRD-777"].name == "Produto Novo"


def test_listar_nao_desliga_a_tela_da_foto():
    """A armadilha mais traiçoeira desta correção.

    `list_all()` chama `load_catalog()`. Se ele devolvesse um dict novo, uma
    simples listagem trocaria a foto por um objeto órfão e a tela voltaria a
    congelar — sem erro, sem sintoma, até alguém gravar.
    """
    repo = SupabaseProductRepository(ClienteFalso(catalogo_falso()), COMPANY)
    catalogo = repo.load_catalog()

    repo.list_all()
    repo.load_catalog()

    ProductService(repo).update_product(conta_admin().session(), "PRD-009",
                                        dados(stock="7"))
    assert catalogo["PRD-009"].stock == "7"


def test_gravar_sem_ter_listado_nao_quebra():
    """Há chamadores que gravam sem nunca ter montado a foto."""
    repo = SupabaseProductRepository(
        ClienteFalso(catalogo_falso(), rpc_resultados={"fn_create_products": "id"}),
        COMPANY,
    )
    assert ProductService(repo).create_product(
        conta_admin().session(), dados(code="PRD-500")) == "PRD-500"


# ======================================== 2. mexer na tela grava no banco


class RepositorioEspiao:
    """Repositório de demonstração que registra o que foi persistido."""

    def __init__(self, catalogo):
        from stockflow.infrastructure.repositories.demo_product_repository import (
            DemoProductRepository,
        )
        self._interno = DemoProductRepository(catalogo)
        self.set_active_calls = []
        self.falhar = False

    def set_active(self, code, active):
        self.set_active_calls.append((code, active))
        if self.falhar:
            raise RuntimeError("conexão recusada")
        self._interno.set_active(code, active)

    def __getattr__(self, nome):
        return getattr(self._interno, nome)


@pytest.fixture
def janela_espia(qapp, request, monkeypatch):
    espioes = []

    def criar(papel=UserRole.ADMIN):
        from stockflow.presentation.demo_products import DEMO_PRODUCTS

        catalogo = dict(DEMO_PRODUCTS)
        espiao = RepositorioEspiao(catalogo)
        monkeypatch.setattr(
            "stockflow.presentation.windows.main_window.build_catalog",
            lambda s: (catalogo, espiao),
        )
        window = MainWindow(conta_por_papel(papel).session())
        espioes.append(window)
        return window, espiao

    request.addfinalizer(lambda: [w.close() for w in espioes])
    return criar


def test_desativar_pela_tabela_persiste(janela_espia):
    """O bug: a linha mudava e nada chegava ao repositório."""
    window, espiao = janela_espia()
    linha = window.estoque_page.produtos[0]
    code = linha[0]

    window.estoque_page.toggle_product_status(linha)

    assert espiao.set_active_calls == [(code, False)]
    assert window.products[code].active is False


def test_reativar_tambem_persiste(janela_espia):
    window, espiao = janela_espia()
    linha = window.estoque_page.produtos[0]

    window.estoque_page.toggle_product_status(linha)
    window.estoque_page.toggle_product_status(linha)

    assert [ativo for _, ativo in espiao.set_active_calls] == [False, True]


def test_falha_ao_persistir_desfaz_a_mudanca_na_tela(janela_espia, monkeypatch):
    """Deixar a linha mostrando o estado novo seria pior do que a falha.

    O usuário sairia convencido de que desativou o produto.
    """
    avisos = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: avisos.append(a[1:3])))

    window, espiao = janela_espia()
    espiao.falhar = True
    linha = window.estoque_page.produtos[0]
    code = linha[0]

    window.estoque_page.toggle_product_status(linha)

    assert window.products[code].active is True, "a tela precisa voltar ao estado real"
    assert isinstance(window.last_save_error, RuntimeError)
    assert avisos, "a falha precisa aparecer para o usuário"


def test_a_porta_exige_set_active_dos_dois_adaptadores():
    """Estar só num adaptador foi o que permitiu o método ficar sem chamador."""
    from stockflow.infrastructure.repositories.demo_product_repository import (
        DemoProductRepository,
    )

    assert hasattr(DemoProductRepository, "set_active")
    assert hasattr(SupabaseProductRepository, "set_active")


# ===================================== 3. reconsultar ao abrir o Estoque


def test_abrir_estoque_reconsulta_quando_ha_banco(qapp, monkeypatch, request):
    """US04: alerta desatualizado é o que o critério proíbe.

    As gravações desta janela já atualizam a foto na hora; o que esta
    reconsulta cobre é a movimentação confirmada por outro caminho.
    """
    from stockflow.presentation.demo_products import DEMO_PRODUCTS

    catalogo = dict(DEMO_PRODUCTS)
    chamadas = []

    class RepoComBanco(RepositorioEspiao):
        def load_catalog(self):
            chamadas.append(1)
            return catalogo

    repo = RepoComBanco(catalogo)
    monkeypatch.setattr(
        "stockflow.presentation.windows.main_window.build_catalog",
        lambda s: (catalogo, repo),
    )
    window = MainWindow(conta_admin().session())
    request.addfinalizer(window.close)
    # Executor síncrono: um teste de UI não tem laço de eventos girando, e a
    # tarefa em segundo plano nunca entregaria o resultado.
    window.executar_em_segundo_plano = executar_agora

    window.show_page("estoque")
    assert chamadas, "abrir a tela precisa reconsultar o catálogo"
    assert window.estoque_page._list_state == "ready"


def test_falha_na_reconsulta_aparece_na_lista(qapp, monkeypatch, request):
    from stockflow.presentation.demo_products import DEMO_PRODUCTS

    catalogo = dict(DEMO_PRODUCTS)

    class RepoQueFalha(RepositorioEspiao):
        def load_catalog(self):
            raise RuntimeError("timeout na consulta")

    monkeypatch.setattr(
        "stockflow.presentation.windows.main_window.build_catalog",
        lambda s: (catalogo, RepoQueFalha(catalogo)),
    )
    window = MainWindow(conta_admin().session())
    request.addfinalizer(window.close)
    window.executar_em_segundo_plano = executar_agora

    window.show_page("estoque")

    assert window.estoque_page._list_state == "error"
    assert "timeout na consulta" in window.estoque_page.load_error_label.text()


def test_modo_demonstracao_nao_reconsulta(qapp, request, monkeypatch):
    """Sem banco não há o que reconsultar: a foto É a fonte."""
    monkeypatch.delenv(backend.BACKEND_VAR, raising=False)
    window = MainWindow(conta_admin().session())
    request.addfinalizer(window.close)

    window.show_page("estoque")

    assert not hasattr(window.product_repository, "load_catalog")
    assert window.estoque_page._list_state == "ready"
