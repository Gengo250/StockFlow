"""Adaptador de catálogo sobre o Supabase, contra um cliente falso.

Não há Postgres nem Supabase neste ambiente, então o que estes testes provam é
o CONTRATO do adaptador: qual função ele chama, com quais argumentos e como
traduz a resposta. Isso é justamente o que um teste de integração não
olharia de perto — e é onde um adaptador erra: mandar `float` para
`numeric(10,2)`, mandar o rótulo da unidade onde o enum espera o código,
mandar `company_id` para uma função que resolve a empresa sozinha.

O que estes testes NÃO provam: que as funções existem no banco com essa
assinatura, e que o papel do usuário tem permissão. Essas duas só a aplicação
da migration e um login real respondem.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from stockflow.application.dto.product_input import ProductInput
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.supabase_product_repository import (
    SupabaseProductRepository,
)

COMPANY = "11111111-1111-1111-1111-111111111111"
PRODUTO_ID = "22222222-2222-2222-2222-222222222222"
CATEGORIA_ID = "33333333-3333-3333-3333-333333333333"


# ------------------------------------------------------------- cliente falso


class RespostaFalsa:
    def __init__(self, data):
        self.data = data


class ConsultaFalsa:
    """Imita o encadeamento `table(...).select(...).eq(...).execute()`.

    Guarda os filtros aplicados para que o teste possa afirmar que o escopo
    de empresa foi mandado — sem isso, um adaptador que esquecesse o `.eq`
    passaria aqui e só falharia em produção, trazendo dado demais.
    """

    def __init__(self, tabela, tabelas, registro):
        self._tabela = tabela
        self._tabelas = tabelas
        self._registro = registro
        self._filtros = {}

    def select(self, colunas):
        self._colunas = colunas
        return self

    def eq(self, coluna, valor):
        self._filtros[coluna] = valor
        return self

    def in_(self, coluna, valores):
        self._filtros[coluna] = list(valores)
        return self

    def limit(self, _n):
        return self

    def order(self, _coluna):
        return self

    def execute(self):
        self._registro.append((self._tabela, dict(self._filtros)))
        linhas = self._tabelas.get(self._tabela, [])
        for coluna, valor in self._filtros.items():
            if isinstance(valor, list):
                linhas = [l for l in linhas if l.get(coluna) in valor]
            else:
                linhas = [l for l in linhas if l.get(coluna) == valor]
        return RespostaFalsa(linhas)


class ClienteFalso:
    def __init__(self, tabelas=None, rpc_resultados=None, rpc_erros=None):
        self.tabelas = tabelas or {}
        self.consultas = []
        self.chamadas_rpc = []
        self._rpc_resultados = rpc_resultados or {}
        self._rpc_erros = rpc_erros or {}

    def table(self, nome):
        return ConsultaFalsa(nome, self.tabelas, self.consultas)

    def rpc(self, nome, args):
        self.chamadas_rpc.append((nome, args))
        cliente = self

        class _Chamada:
            def execute(self):
                if nome in cliente._rpc_erros:
                    raise cliente._rpc_erros[nome]
                return RespostaFalsa(cliente._rpc_resultados.get(nome))

        return _Chamada()


class ErroDoPostgrest(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.message = message
        self.code = code


def catalogo_falso():
    return {
        "products": [
            {"id": PRODUTO_ID, "company_id": COMPANY, "barcode": "PRD-009",
             "name": "Monitor LG UltraWide 34\"", "sell_price": "2499.90",
             "buy_price": "1850.00", "unit": "UN", "stock": 18,
             "item_category": CATEGORIA_ID, "active": True},
        ],
        "categories": [
            {"id": CATEGORIA_ID, "company_id": COMPANY, "name": "Eletrônicos"},
        ],
        "product_stock": [
            {"product_id": PRODUTO_ID, "min_quantity": 5},
        ],
    }


def repositorio(cliente=None, **kwargs):
    return SupabaseProductRepository(
        cliente or ClienteFalso(catalogo_falso()), COMPANY, **kwargs
    )


def dados(**overrides):
    base = dict(
        code="PRD-010", name="Teclado mecânico", category="Periféricos",
        unit="Unidade (UN)", sale_price="R$ 459,90", cost="R$ 280,00",
        stock="7", active=True, minimum_stock=10,
    )
    base.update(overrides)
    return ProductInput(**base)


def args_de(cliente, nome):
    return next(a for n, a in cliente.chamadas_rpc if n == nome)


# ------------------------------------------------------------------- leitura


def test_catalogo_traduz_a_linha_do_banco_para_o_produto_da_tela():
    produto = repositorio().load_catalog()["PRD-009"]

    assert produto.code == "PRD-009"            # barcode vira code
    assert produto.category == "Eletrônicos"    # uuid resolvido para nome
    assert produto.unit == "Unidade (UN)"       # enum vira rótulo
    assert produto.sale_price == "R$ 2.499,90"  # numeric vira texto formatado
    assert produto.cost == "R$ 1.850,00"
    assert produto.stock == "18"
    assert produto.minimum_stock == 5           # veio de product_stock


def test_status_e_derivado_do_minimo_do_produto():
    """Saldo 11 cai numa faixa diferente a cada mínimo.

    Expõe quem ignora `product_stock` e usa um limiar fixo: o mesmo saldo é
    Normal, Atenção ou Baixo conforme o mínimo DO PRODUTO. As faixas são as
    de `public.fn_stock_state`.
    """
    def status_com(minimo):
        tabelas = catalogo_falso()
        tabelas["products"][0]["stock"] = 11
        tabelas["product_stock"][0]["min_quantity"] = minimo
        return repositorio(ClienteFalso(tabelas)).load_catalog()["PRD-009"].stock_status

    assert status_com(5) == "Normal"     # 11 >= 5 × 1,2
    assert status_com(10) == "Atenção"   # 11 > 10, mas 11 < 12
    assert status_com(20) == "Baixo"     # 11 <= 20


def test_produto_sem_linha_de_minimo_fica_sem_configuracao():
    """Sem linha em `product_stock`, não há mínimo — e sem mínimo não há alerta.

    Espelha o `COALESCE(ps.min_quantity, 0)` da `vw_stock_situation`. Supor um
    limiar plausível aqui faria o produto alertar por uma regra que ninguém
    configurou, violando o critério de exclusão da US04.
    """
    tabelas = catalogo_falso()
    tabelas["products"][0]["stock"] = 1
    tabelas["product_stock"] = []
    produto = repositorio(ClienteFalso(tabelas)).load_catalog()["PRD-009"]

    assert produto.minimum_stock == 0
    assert produto.stock_status == "Normal"


def test_toda_leitura_e_escopada_pela_empresa():
    cliente = ClienteFalso(catalogo_falso())
    repositorio(cliente).load_catalog()

    por_empresa = [f for t, f in cliente.consultas if t in ("products", "categories")]
    assert por_empresa, "nenhuma consulta registrada"
    assert all(f.get("company_id") == COMPANY for f in por_empresa)


def test_minimos_sao_resolvidos_em_uma_consulta_so():
    """N+1 na abertura do Estoque é ida à rede por produto."""
    cliente = ClienteFalso(catalogo_falso())
    repositorio(cliente).load_catalog()
    assert sum(1 for t, _ in cliente.consultas if t == "product_stock") == 1


def test_get_devolve_none_para_codigo_inexistente():
    assert repositorio().get("PRD-404") is None


def test_get_devolve_produto_inativo():
    """US02: quem recusa o inativo é a política, não a leitura."""
    tabelas = catalogo_falso()
    tabelas["products"][0]["active"] = False
    produto = repositorio(ClienteFalso(tabelas)).get("PRD-009")
    assert produto is not None and produto.active is False


def test_exists_responde_pelo_codigo():
    repo = repositorio()
    assert repo.exists("PRD-009") is True
    assert repo.exists("PRD-404") is False


def test_proximo_codigo_continua_a_numeracao_da_empresa():
    assert repositorio().next_code() == "PRD-010"


def test_categorias_vem_do_banco_e_unidades_do_enum():
    repo = repositorio()
    assert repo.list_active_categories() == ("Eletrônicos",)
    assert repo.is_category_active("Eletrônicos") is True
    assert repo.is_category_active("Categoria Fantasma") is False
    assert "Unidade (UN)" in repo.list_active_units()
    assert repo.is_unit_active("Unidade (UN)") is True


# ------------------------------------------------------------------ escrita


def test_create_chama_a_funcao_com_os_tipos_do_banco():
    cliente = ClienteFalso(catalogo_falso(), rpc_resultados={"fn_create_products": PRODUTO_ID})
    assert repositorio(cliente).create(dados()) == "PRD-010"

    args = args_de(cliente, "fn_create_products")
    assert args["p_company_id"] == COMPANY
    assert args["p_barcode"] == "PRD-010"
    assert args["p_sell_price"] == "459.90"   # texto decimal, nunca float
    assert args["p_buy_price"] == "280.00"
    assert args["p_unit"] == "UN"             # enum, não o rótulo da tela
    assert args["p_stock"] == 7               # inteiro, não "7"
    assert args["p_item_category"] == "Periféricos"  # nome; a função resolve o id


def test_create_grava_o_estoque_minimo_na_tabela_propria():
    cliente = ClienteFalso(catalogo_falso(), rpc_resultados={"fn_create_products": PRODUTO_ID})
    repositorio(cliente).create(dados(minimum_stock=3))

    args = args_de(cliente, "fn_set_min_stock")
    assert args == {"p_product_id": PRODUTO_ID, "p_min": 3}


def test_create_ativo_nao_gasta_chamada_de_situacao():
    """A coluna nasce `true`; chamar fn_set_product_active seria request à toa."""
    cliente = ClienteFalso(catalogo_falso(), rpc_resultados={"fn_create_products": PRODUTO_ID})
    repositorio(cliente).create(dados(active=True))
    assert not any(n == "fn_set_product_active" for n, _ in cliente.chamadas_rpc)


def test_create_inativo_desativa_logo_apos_criar():
    cliente = ClienteFalso(catalogo_falso(), rpc_resultados={"fn_create_products": PRODUTO_ID})
    repositorio(cliente).create(dados(active=False))
    assert args_de(cliente, "fn_set_product_active") == {
        "p_product_id": PRODUTO_ID, "p_active": False
    }


def test_update_resolve_o_uuid_e_nao_manda_company_id():
    """`fn_update_products` resolve a empresa pela linha do produto.

    Mandar `p_company_id` daqui reabriria o buraco que a função fecha: editar
    produto de outra empresa bastando informar uma onde o usuário é ADMIN.
    """
    cliente = ClienteFalso(catalogo_falso())
    repositorio(cliente).update("PRD-009", dados(code="PRD-009"))

    args = args_de(cliente, "fn_update_products")
    assert args["p_product_id"] == PRODUTO_ID
    assert "p_company_id" not in args


def test_update_aplica_a_situacao_por_funcao_separada():
    cliente = ClienteFalso(catalogo_falso())
    repositorio(cliente).update("PRD-009", dados(code="PRD-009", active=False))

    assert "p_active" not in args_de(cliente, "fn_update_products")
    assert args_de(cliente, "fn_set_product_active")["p_active"] is False


def test_update_de_codigo_inexistente_levanta_lookup():
    with pytest.raises(LookupError, match="PRD-404"):
        repositorio().update("PRD-404", dados(code="PRD-404"))


def test_set_active_usa_soft_delete():
    cliente = ClienteFalso(catalogo_falso())
    repositorio(cliente).set_active("PRD-009", False)
    assert args_de(cliente, "fn_set_product_active") == {
        "p_product_id": PRODUTO_ID, "p_active": False
    }


# -------------------------------------------------------------- permissão


@pytest.mark.parametrize("erro", [
    ErroDoPostgrest("Sem permissão para cadastrar produtos nesta empresa", code="42501"),
    ErroDoPostgrest("permission denied for function fn_create_products"),
])
def test_recusa_do_banco_vira_erro_de_dominio(erro):
    """A `MainWindow` só captura `PermissionDeniedError`.

    Deixar a exceção crua do cliente HTTP subir faria a tela mostrar um
    traceback onde deveria aparecer a mensagem de permissão da US01.
    """
    cliente = ClienteFalso(catalogo_falso(), rpc_erros={"fn_create_products": erro})
    repo = repositorio(cliente, role=UserRole.SELLER)

    with pytest.raises(PermissionDeniedError) as capturado:
        repo.create(dados())

    assert "cadastrar produtos" in str(capturado.value)
    assert "SELLER" in str(capturado.value)


def test_erro_que_nao_e_de_permissao_sobe_como_veio():
    """Categoria inexistente não é falta de permissão, e não pode virar uma."""
    erro = ErroDoPostgrest("Item category doesnt exist", code="23503")
    cliente = ClienteFalso(catalogo_falso(), rpc_erros={"fn_create_products": erro})

    with pytest.raises(ErroDoPostgrest):
        repositorio(cliente).create(dados())
