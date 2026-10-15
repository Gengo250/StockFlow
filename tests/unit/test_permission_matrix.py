"""A matriz de permissões é a fonte única de quem vê e quem grava (H14).

Antes desta matriz, a verdade de permissão vivia em seis lugares que nada
forçava a concordar: os `frozenset` de `domain/permissions.py`, o
`RESTRICTED_PAGES` da `MainWindow`, os toggles manuais de `apply_session`, as
chamadas `sidebar.set_item_visible`, cada função SQL e cada policy. Trocar
`ARRAY['ADMIN','STOCK']` no SQL não deixava nada vermelho.

Estes testes existem para que deixe. Eles leem `database/code/` como texto —
não há Postgres aqui, pelo mesmo motivo de `tests/test_schema_declarativo.py`.
"""

import re
from pathlib import Path

import pytest

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.permissions import (
    PERMISSION_MATRIX,
    TODOS_OS_PAPEIS,
    Area,
    pode_gravar,
    pode_ver,
)

RAIZ = Path(__file__).resolve().parents[2]
CODE = RAIZ / "database" / "code"

ADMIN, STOCK, SELLER = UserRole.ADMIN, UserRole.STOCK, UserRole.SELLER


def _sem_comentarios(texto: str) -> str:
    """Comentário não decide permissão.

    Os arquivos deste projeto explicam as regras em comentários que citam
    `fn_has_role` e papéis; lidos como código, eles inventariam alçadas que
    ninguém concedeu.
    """
    return re.sub(r"--[^\n]*", "", texto)


def _sql() -> str:
    arquivos = sorted(CODE.rglob("*.sql"))
    return "\n".join(_sem_comentarios(p.read_text(encoding="utf-8")) for p in arquivos)


def _corpo_da_funcao(sql: str, nome: str) -> str | None:
    """Texto de uma função, do seu CREATE até o próximo CREATE de topo."""
    abertura = re.search(
        rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?{nome}\b", sql
    )
    if abertura is None:
        return None
    resto = sql[abertura.end() :]
    proxima = re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|POLICY|TABLE)\b", resto)
    return resto[: proxima.start()] if proxima else resto


def _corpo_da_policy(sql: str, nome: str) -> str | None:
    """Texto de uma policy, do seu CREATE POLICY até o próximo CREATE."""
    abertura = re.search(rf"CREATE\s+POLICY\s+{nome}\b", sql)
    if abertura is None:
        return None
    resto = sql[abertura.end() :]
    proxima = re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|POLICY|TABLE)\b", resto)
    return resto[: proxima.start()] if proxima else resto


def papeis_da_fonte(nome: str) -> frozenset[UserRole] | None:
    """Papéis que o SQL exige na função ou policy `nome`.

    Resolve os três jeitos que este projeto usa para decidir alçada:
    `fn_is_admin` (só ADMIN), `fn_is_member` (os três) e `fn_has_role` com um
    `ARRAY[...]` explícito. Devolve `None` quando a fonte não existe no SQL,
    para que fonte inventada na matriz apareça como falha e não como acerto.
    """
    sql = _sql()
    corpo = _corpo_da_funcao(sql, nome) or _corpo_da_policy(sql, nome)
    if corpo is None:
        return None

    arrays = re.findall(
        r"fn_has_role\s*\(.*?ARRAY\s*\[(.*?)\]", corpo, flags=re.DOTALL
    )
    if arrays:
        papeis = {
            frozenset(
                UserRole.from_value(valor)
                for valor in re.findall(r"'(\w+)'", array)
            )
            for array in arrays
        }
        # Função que checa alçadas diferentes em caminhos diferentes não tem
        # "a" lista de papéis, e a matriz não conseguiria representá-la.
        assert len(papeis) == 1, f"{nome} exige listas de papéis divergentes: {papeis}"
        return next(iter(papeis))

    if re.search(r"fn_is_member\s*\(", corpo):
        return TODOS_OS_PAPEIS
    if re.search(r"fn_is_admin\s*\(", corpo):
        return frozenset({ADMIN})
    return None


#: Policy de tabela que governa a LEITURA de cada área no Postgres. Usada para
#: provar que a aplicação nunca é mais permissiva que o banco. Áreas sem
#: tabela própria ficam de fora.
POLICY_DE_LEITURA = {
    "estoque": "products_select",
    "produtos": "products_select",
    "movimentacoes": "stock_movements_select",
    "fornecedores": "suppliers_select",
    "clientes": "clients_select",
    "vendas": "sales_select",
}

AREAS = sorted(PERMISSION_MATRIX)
COM_ESCRITA = sorted(n for n, a in PERMISSION_MATRIX.items() if a.gravar)


def test_toda_chave_de_menu_tem_decisao_de_permissao():
    """Item de menu novo não entra sem alguém decidir quem o vê.

    Sem este teste, uma área nova nasce visível para os três papéis por
    omissão — que é exatamente como `clientes` e `vendas` ficaram fora do
    `RESTRICTED_PAGES` sem ninguém decidir isso.
    """
    from stockflow.presentation.widgets.sidebar import MENU_ITEMS, SYSTEM_ITEMS

    chaves = {chave for chave, _, _ in MENU_ITEMS + SYSTEM_ITEMS}
    faltando = sorted(chaves - set(PERMISSION_MATRIX))

    assert faltando == [], f"áreas de menu sem entrada na matriz: {faltando}"


@pytest.mark.parametrize("nome", COM_ESCRITA)
def test_escrita_da_matriz_bate_com_o_sql(nome):
    """`area.gravar` é igual ao `ARRAY[...]` que a função SQL exige."""
    area = PERMISSION_MATRIX[nome]
    do_sql = papeis_da_fonte(area.fonte_gravar)

    assert do_sql is not None, (
        f"{nome}: fonte de escrita '{area.fonte_gravar}' não existe em database/code/"
    )
    assert area.gravar == do_sql, (
        f"{nome}: matriz grava {sorted(area.gravar)}, "
        f"mas {area.fonte_gravar} exige {sorted(do_sql)}"
    )


@pytest.mark.parametrize(
    "nome", sorted(n for n, a in PERMISSION_MATRIX.items() if a.fonte_ver)
)
def test_leitura_da_matriz_bate_com_o_sql(nome):
    """`area.ver` é igual ao que a fonte de leitura declarada exige."""
    area = PERMISSION_MATRIX[nome]
    do_sql = papeis_da_fonte(area.fonte_ver)

    assert do_sql is not None, (
        f"{nome}: fonte de leitura '{area.fonte_ver}' não existe em database/code/"
    )
    assert area.ver == do_sql, (
        f"{nome}: matriz vê {sorted(area.ver)}, "
        f"mas {area.fonte_ver} exige {sorted(do_sql)}"
    )


@pytest.mark.parametrize("nome", sorted(POLICY_DE_LEITURA))
def test_a_aplicacao_nunca_e_mais_permissiva_que_a_policy(nome):
    """A app pode ser mais estrita que a RLS; nunca mais frouxa.

    `movimentacoes` é o caso deliberadamente mais estrito: a policy
    `stock_movements_select` usa `fn_is_member` e deixaria o vendedor ler o
    histórico, mas a aplicação segue a alçada de escrita. Mais frouxa, porém,
    seria uma tela prometendo dado que o Postgres recusa — e o usuário veria
    uma lista vazia sem explicação.
    """
    area = PERMISSION_MATRIX[nome]
    da_policy = papeis_da_fonte(POLICY_DE_LEITURA[nome])

    assert da_policy is not None
    assert area.ver <= da_policy, (
        f"{nome}: a aplicação deixa {sorted(area.ver - da_policy)} abrir a área, "
        f"mas a policy {POLICY_DE_LEITURA[nome]} recusa esse papel"
    )


@pytest.mark.parametrize("nome", AREAS)
def test_quem_grava_tambem_ve(nome):
    """Alçada de escrita sem leitura seria uma tela que não abre e grava."""
    area = PERMISSION_MATRIX[nome]

    assert area.gravar <= area.ver, (
        f"{nome}: {sorted(area.gravar - area.ver)} grava sem poder abrir a área"
    )


@pytest.mark.parametrize("papel", [ADMIN, STOCK, SELLER])
@pytest.mark.parametrize("nome", AREAS)
def test_consulta_da_matriz_responde_para_os_tres_papeis(nome, papel):
    """`pode_ver`/`pode_gravar` leem a matriz, e não uma cópia paralela."""
    area = PERMISSION_MATRIX[nome]

    assert pode_ver(papel, nome) is (papel in area.ver)
    assert pode_gravar(papel, nome) is (papel in area.gravar)


@pytest.mark.parametrize("nome", AREAS)
def test_sessao_ausente_nao_ve_nem_grava(nome):
    """Falha fechada: sem sessão, nega — inclusive nas áreas sem gate."""
    assert pode_ver(None, nome) is False
    assert pode_gravar(None, nome) is False


def test_area_desconhecida_nega_em_vez_de_liberar():
    """Chave errada não pode virar porta aberta."""
    assert pode_ver(ADMIN, "area-que-nao-existe") is False
    assert pode_gravar(ADMIN, "area-que-nao-existe") is False


def test_o_espelhamento_pegaria_uma_divergencia():
    """Prova que os testes acima conseguem falhar.

    Um guard que não sabe falhar não guarda nada: se `papeis_da_fonte` parasse
    de achar as regras e passasse a devolver sempre o mesmo conjunto, todos os
    testes de espelhamento ficariam verdes sobre SQL nenhum. Aqui uma área
    deliberadamente errada é comparada pelo mesmo caminho.
    """
    errada = Area(
        ver=TODOS_OS_PAPEIS,
        gravar=TODOS_OS_PAPEIS,  # o SQL exige só ADMIN e STOCK
        fonte_ver="products_select",
        fonte_gravar="fn_update_products",
    )

    assert papeis_da_fonte(errada.fonte_gravar) == frozenset({ADMIN, STOCK})
    assert errada.gravar != papeis_da_fonte(errada.fonte_gravar)


def test_fonte_inventada_nao_passa_despercebida():
    """Fonte que não existe no SQL devolve `None`, nunca um acerto vazio."""
    assert papeis_da_fonte("fn_que_nunca_existiu") is None


def test_a_funcao_de_ajuste_exige_a_mesma_alcada_das_movimentacoes():
    """H11 reaproveita a área `movimentacoes`; o SQL tem que concordar.

    Sem este teste, alguém troca `fn_has_role(ADMIN, STOCK)` por
    `fn_is_member` dentro de `fn_register_adjustment` e nada fica vermelho:
    a matriz continua apontando para `fn_register_movement`, que não mudou.
    """
    do_sql = papeis_da_fonte("fn_register_adjustment")

    assert do_sql is not None, "fn_register_adjustment não existe em database/code/"
    assert do_sql == PERMISSION_MATRIX["movimentacoes"].gravar, (
        f"fn_register_adjustment exige {sorted(do_sql)}, mas a área "
        f"movimentacoes grava {sorted(PERMISSION_MATRIX['movimentacoes'].gravar)}"
    )
