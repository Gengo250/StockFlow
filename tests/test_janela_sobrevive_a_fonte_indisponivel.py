"""Uma fonte de dados indisponível não pode impedir o login de abrir o app.

Caso real que originou estes testes: o banco remoto estava sem a coluna
`sales.client_name`, `VendasPage.__init__` consultava o histórico de vendas sem
isolamento, e a exceção subia por `_create_pages` até `MainWindow.__init__`. O
usuário autenticava com sucesso e recebia "Não foi possível abrir o StockFlow" —
sem Estoque, sem Produtos, sem Clientes, sem Usuários, nenhum dos quais depende
de vendas.

O padrão correto já existia no projeto: `SuppliersPage.reload_table` captura a
falha, guarda em `last_error`, mostra o aviso na própria tela e deixa a página
em pé. Estes testes cobram esse mesmo comportamento no caminho de construção.
"""

import pytest

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.windows import main_window
from stockflow.presentation.windows.main_window import MainWindow

FALHA = "column sales.client_name does not exist"


class FonteIndisponivel:
    """Repositório que falha como o Supabase falha: na consulta, não no build.

    `build_sale_repository` devolve o objeto sem tocar na rede; quem estoura é
    a primeira leitura. Um fake que falhasse no construtor testaria um cenário
    que não acontece.
    """

    def __init__(self, erro=FALHA):
        self._erro = erro
        self.consultas = 0

    def list_all(self):
        self.consultas += 1
        raise RuntimeError(self._erro)

    def register(self, *args, **kwargs):
        raise RuntimeError(self._erro)


@pytest.fixture
def vendas_fora_do_ar(monkeypatch):
    """Só a fonte de VENDAS cai; as demais continuam de pé, como no caso real."""
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    fonte = FonteIndisponivel()
    monkeypatch.setattr(
        main_window, "build_sale_repository", lambda session, products: fonte
    )
    return fonte


@pytest.fixture
def janela(qapp, request):
    abertas = []

    def criar(sessao):
        window = MainWindow(sessao)
        abertas.append(window)
        return window

    request.addfinalizer(lambda: [w.close() for w in abertas])
    return criar


def sessao(papel=UserRole.ADMIN):
    return conta_por_papel(papel).session()


def test_a_janela_abre_mesmo_com_a_fonte_de_vendas_fora_do_ar(janela, vendas_fora_do_ar):
    """O critério é este: autenticou, a interface tem que abrir."""
    window = janela(sessao())

    assert window is not None
    assert vendas_fora_do_ar.consultas > 0, (
        "o teste não exercitou o caminho de falha: ninguém consultou vendas"
    )


def test_as_telas_que_nao_dependem_de_vendas_continuam_inteiras(janela, vendas_fora_do_ar):
    """Estoque não tem relação com o histórico de vendas e não pode cair junto."""
    window = janela(sessao())

    assert window.products, "o catálogo sumiu por causa de uma falha em vendas"
    assert window.show_page("estoque") is True
    assert window.show_page("usuarios") is True
    assert window.estoque_page.stock_table.table.rowCount() > 0


def test_a_tela_de_vendas_relata_a_falha_em_vez_de_fingir_lista_vazia(
    janela, vendas_fora_do_ar
):
    """Histórico vazio e histórico indisponível não são a mesma coisa.

    Mostrar "nenhuma venda" quando a consulta falhou faz o usuário concluir que
    não vendeu nada — e é a conclusão errada.
    """
    window = janela(sessao())

    assert window.vendas_page.last_error is not None
    assert FALHA in str(window.vendas_page.last_error)


def test_a_falha_de_vendas_nao_vira_erro_de_salvamento(janela, vendas_fora_do_ar):
    """`last_save_error` é sobre gravação; carga que falhou não é gravação."""
    window = janela(sessao())

    assert window.last_save_error is None


def test_vendas_volta_ao_normal_quando_a_fonte_se_recupera(janela, monkeypatch):
    """Falha transitória não pode deixar a tela permanentemente quebrada."""
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    fonte = FonteIndisponivel()
    monkeypatch.setattr(
        main_window, "build_sale_repository", lambda session, products: fonte
    )
    window = janela(sessao())
    assert window.vendas_page.last_error is not None

    # A fonte se recupera: a próxima leitura devolve histórico de verdade.
    fonte.list_all = lambda: []
    window.vendas_page.reload_sales()

    assert window.vendas_page.last_error is None


# ----------------------------------------------------- fornecedores

def test_a_janela_abre_com_a_fonte_de_fornecedores_fora_do_ar(janela, monkeypatch):
    """Mesma causa raiz, outra consulta: `_create_pages` lê fornecedores.

    `MainWindow._create_pages` chama `supplier_service.list_suppliers` para
    alimentar o combo de Movimentações. É uma consulta de rede no caminho de
    construção, igual à de vendas — e derrubaria a janela pelo mesmo motivo.
    """
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")

    class SemFornecedores:
        def list_suppliers(self, session):
            raise RuntimeError("relation \"suppliers\" does not exist")

    monkeypatch.setattr(
        main_window, "SupplierService", lambda *a, **k: SemFornecedores()
    )
    window = janela(sessao())

    assert window is not None
    assert window.show_page("estoque") is True
    # Movimentações continua navegável, apenas sem fornecedor a oferecer.
    assert window.show_page("movimentacoes") is True
