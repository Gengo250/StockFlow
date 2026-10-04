"""US03 — o saldo vem das movimentações confirmadas.

Não há Postgres neste ambiente, então a verificação é ESTÁTICA: lê o SQL
declarativo em `database/code` e cobra as propriedades que sustentam o
critério "considerar somente movimentações confirmadas na composição do
saldo".

O que um teste estático consegue provar aqui é mais do que parece. O critério
se sustenta em quatro afirmações estruturais, e todas são verificáveis no
texto:

1. existe onde registrar movimentação, com situação própria;
2. a soma que vira saldo filtra por CONFIRMADA;
3. ninguém escreve `products.stock` por fora — senão o saldo deixaria de
   corresponder às linhas no primeiro cadastro;
4. a transição de situação dispara o recálculo.

O que ele NÃO prova: que o SQL roda. Isso só a aplicação da migration
responde, e a própria migration termina com um bloco que levanta exceção se
algum saldo divergir da soma das confirmadas.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CODE = RAIZ / "database" / "code"


def sql(*partes) -> str:
    return (CODE.joinpath(*partes)).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tudo():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(CODE.rglob("*.sql")))


def corpo_da_rotina(texto, nome):
    achado = re.search(
        rf"CREATE OR REPLACE FUNCTION (?:public\.){nome}\s*\(.*?\$\$;", texto, re.S | re.I
    )
    assert achado, f"rotina {nome} não encontrada"
    return achado.group(0)


# ------------------------------------------- 1. onde registrar movimentação


def test_a_tabela_de_movimentacoes_existe_com_o_minimo_necessario():
    corpo = sql("tables", "05_movements.sql")
    for coluna in ("product_id", "kind", "quantity", "status", "confirmed_on"):
        assert re.search(rf"^\s*{coluna}\s", corpo, re.M), coluna


def test_movimentacao_nasce_pendente():
    """Registrar não é confirmar — é essa distinção que a US03 pede."""
    corpo = sql("tables", "05_movements.sql")
    assert re.search(r"status\s+public\.movement_status\s+NOT NULL\s+DEFAULT\s+'PENDENTE'",
                     corpo, re.I)


def test_quantidade_e_sempre_positiva():
    """O sinal vem da espécie (ENTRADA/SAIDA), nunca da quantidade.

    Quantidade negativa deixaria o sinal escondido no dado e permitiria uma
    "ENTRADA de -5" que ninguém lê como saída.
    """
    corpo = sql("tables", "05_movements.sql")
    assert re.search(r"quantity\s+integer\s+NOT NULL\s+CHECK\s*\(\s*quantity\s*>\s*0\s*\)",
                     corpo, re.I)


# --------------------------------------------------- 2. a soma é filtrada


def test_o_saldo_soma_apenas_as_confirmadas():
    """O coração do critério."""
    corpo = corpo_da_rotina(sql("procedures", "04a_movements.sql"), "fn_confirmed_balance")

    assert "stock_movements" in corpo
    assert re.search(r"status\s*=\s*'CONFIRMADA'", corpo), (
        "a soma precisa filtrar por CONFIRMADA; sem isso pendentes e "
        "canceladas entrariam no saldo"
    )
    # ENTRADA soma, SAIDA subtrai.
    assert re.search(r"WHEN\s+'ENTRADA'\s+THEN\s+m\.quantity\s+ELSE\s+-\s*m\.quantity",
                     corpo, re.I)


def test_pendente_e_cancelada_sao_situacoes_possiveis():
    """Sem elas, "confirmada" não significaria nada."""
    corpo = sql("tables", "05_movements.sql")
    achado = re.search(r"CREATE TYPE public\.movement_status AS ENUM \((.*?)\)", corpo, re.S)
    assert achado
    situacoes = set(re.findall(r"'(\w+)'", achado.group(1)))
    assert {"PENDENTE", "CONFIRMADA", "CANCELADA"} <= situacoes


# ------------------------------------------ 3. ninguém escreve o saldo direto


@pytest.mark.parametrize("rotina", ["fn_create_products", "fn_update_products"])
def test_cadastro_e_edicao_nao_escrevem_o_saldo(rotina):
    """A regressão que quebraria o critério inteiro.

    Enquanto estas funções escreviam `products.stock`, o saldo era um número
    digitado e não existia movimentação correspondente. Se alguém devolver o
    `stock` ao INSERT/UPDATE, o saldo volta a divergir da soma na primeira
    movimentação seguinte — e o trigger sobrescreveria o valor sem aviso.
    """
    corpo = corpo_da_rotina(sql("procedures", "05_catalog.sql"), rotina)

    # Registra movimentação em vez de tocar a coluna.
    assert "fn_register_movement" in corpo, (
        f"{rotina} precisa registrar movimentação para mexer no saldo"
    )

    if rotina == "fn_update_products":
        assert not re.search(r"^\s*SET\s+.*\bstock\s*=", corpo, re.M | re.I)
        assert not re.search(r"\bstock\s*=\s*COALESCE\(p_stock", corpo, re.I), (
            "o UPDATE não pode mais atribuir stock diretamente"
        )
    else:
        # O INSERT informa zero; o saldo pedido vira a primeira movimentação.
        insert = re.search(r"INSERT INTO public\.products\s*\((.*?)\)\s*VALUES\s*\((.*?)\)",
                           corpo, re.S | re.I)
        assert insert, "INSERT de products não encontrado"
        colunas = [c.strip().lower() for c in insert.group(1).split(",")]
        valores = [v.strip() for v in insert.group(2).split(",")]
        assert valores[colunas.index("stock")] == "0", (
            "o produto precisa nascer com saldo zero; o saldo informado vira "
            "movimentação confirmada logo depois"
        )


# ------------------------------------------ 4. a confirmação move o saldo


def test_a_mudanca_de_situacao_recalcula_o_saldo():
    corpo = sql("triggers", "04_stock_movements.sql")

    assert re.search(r"AFTER\s+INSERT\s+OR\s+UPDATE\s+OR\s+DELETE\s+ON\s+public\.stock_movements",
                     corpo, re.I), (
        "o recálculo precisa cobrir as três operações: confirmar é um UPDATE, "
        "e excluir uma confirmada também muda o saldo"
    )
    assert "fn_confirmed_balance" in corpo, (
        "o trigger precisa usar a MESMA soma da função; uma segunda cópia da "
        "expressão divergiria dela com o tempo"
    )


def test_confirmar_so_vale_para_pendente():
    """Confirmar duas vezes não pode somar duas vezes."""
    corpo = corpo_da_rotina(sql("procedures", "04a_movements.sql"), "fn_confirm_movement")
    assert re.search(r"v_status\s*<>\s*'PENDENTE'", corpo, re.I)


def test_movimentacao_exige_papel_de_estoque():
    for rotina in ("fn_register_movement", "fn_confirm_movement", "fn_cancel_movement"):
        corpo = corpo_da_rotina(sql("procedures", "04a_movements.sql"), rotina)
        assert "fn_has_role" in corpo, rotina
        assert "ADMIN" in corpo and "STOCK" in corpo, rotina


def test_movimentacao_nao_atravessa_empresas():
    """Ser STOCK numa empresa não pode movimentar o estoque de outra."""
    corpo = corpo_da_rotina(sql("procedures", "04a_movements.sql"), "fn_register_movement")
    assert re.search(r"FROM public\.products\s*\n?\s*WHERE id = p_product_id\s+AND company_id = p_company_id",
                     corpo, re.I | re.S)


# ------------------------------------------------- consulta de alerta (US04)


def test_a_view_de_alerta_implementa_os_criterios_da_us04():
    corpo = sql("views", "02_stock_alerts.sql")

    # saldo MENOR OU IGUAL ao mínimo: o `=` é o critério "inclui saldo igual".
    assert re.search(r"current_balance\s*<=\s*s?\.?min_quantity", corpo, re.I)
    # mínimo CONFIGURADO: exclui quem não tem. O filtro é por presença, não
    # por valor — mínimo zero é uma configuração explícita ("avise quando
    # acabar") e precisa alertar; só o NULL, que significa "ninguém
    # configurou", fica de fora.
    assert re.search(r"min_quantity\s+IS\s+NOT\s+NULL", corpo, re.I)
    # inativos já saem de vw_stock_situation, que filtra por p.active.
    assert "vw_stock_situation" in corpo
    assert re.search(r"WHERE\s+p\.active", sql("views", "01_stock_situation.sql"), re.I)


def test_a_migration_confere_o_invariante_antes_de_terminar(tudo):
    """A migration não pode se declarar bem-sucedida sem checar o saldo."""
    migration = (RAIZ / "database" / "supabase" / "migrations"
                 / "20261004140000_stock_movements.sql").read_text(encoding="utf-8")

    assert "fn_confirmed_balance" in migration
    assert re.search(r"RAISE EXCEPTION 'Saldo não bate com as movimentações confirmadas",
                     migration)
    # E a carga inicial, sem a qual todo saldo existente viraria zero.
    assert re.search(r"INSERT INTO public\.stock_movements", migration)
    assert "Saldo inicial migrado" in migration
