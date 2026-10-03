"""Coerência estática das migrations em database/supabase/migrations.

Não há Postgres, psql nem Supabase CLI neste ambiente, então estes testes
validam estaticamente a ordem de aplicação das migrations e a coerência entre
as colunas declaradas nas tabelas e as colunas usadas pelas funções.

As migrations passaram a conviver com dois estilos de nome: as antigas geradas
pelo compilador (`<ts>_<pasta>_<arquivo>.sql`) e as do Supabase CLI
(`<ts>_fn_*.sql`, `<ts>_01_*.sql`). Os testes aceitam os dois e cobram apenas
o que importa para a aplicação: timestamp válido, ordem crescente e
dependências criadas antes do uso.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
MIGRATIONS = RAIZ / "database" / "supabase" / "migrations"


def arquivos():
    return sorted(MIGRATIONS.glob("*.sql"))


def sql_completo():
    return "\n".join(f.read_text(encoding="utf-8") for f in arquivos())


def corpo_da_tabela(nome, sql=None):
    """Bloco entre parênteses do CREATE TABLE, com ou sem prefixo de schema.

    `sql` permite apontar o helper para outra fonte (ex.: database/code);
    sem ele, continua lendo as migrations.
    """
    achado = re.search(
        rf"CREATE TABLE (?:public\.)?{nome}\s*\((.*?)\n\);",
        sql_completo() if sql is None else sql,
        re.S | re.I,
    )
    assert achado, f"tabela {nome} não encontrada"
    return achado.group(1)


IGNORAR_NA_TABELA = (
    "CHECK", "CONSTRAINT", "PRIMARY KEY", "FOREIGN KEY",
    "UNIQUE", "REFERENCES", "ON ",
)


def linhas_de_coluna(nome, sql=None):
    for linha in corpo_da_tabela(nome, sql).splitlines():
        linha = linha.strip().rstrip(",")
        if not linha or linha.upper().startswith(IGNORAR_NA_TABELA):
            continue
        yield linha


def colunas_da_tabela(nome, sql=None):
    return [linha.split()[0].lower() for linha in linhas_de_coluna(nome, sql)]


def colunas_obrigatorias(nome):
    """NOT NULL sem DEFAULT: o INSERT precisa informar explicitamente."""
    obrigatorias = set()
    for linha in linhas_de_coluna(nome):
        alto = linha.upper()
        if "NOT NULL" in alto and "DEFAULT" not in alto:
            obrigatorias.add(linha.split()[0].lower())
    return obrigatorias


def corpo_da_rotina(nome):
    achado = re.search(
        rf"CREATE OR REPLACE (?:FUNCTION|PROCEDURE) (?:public\.)?{nome}\s*\(.*?\$\$;",
        sql_completo(),
        re.S | re.I,
    )
    assert achado, f"rotina {nome} não encontrada"
    return achado.group(0)


# ------------------------------------------------------ nomes e ordem

def test_todas_as_migrations_tem_timestamp_valido():
    for arquivo in arquivos():
        assert re.match(r"^\d{14}_[A-Za-z0-9_\-]+\.sql$", arquivo.name), arquivo.name


def test_timestamps_sao_crescentes_e_unicos():
    stamps = [a.name[:14] for a in arquivos()]
    assert stamps == sorted(stamps)
    assert len(stamps) == len(set(stamps))


# ------------------------------------------------- coerência do schema

def test_tabelas_esperadas_existem():
    sql = sql_completo()
    for tabela in ("access_register", "register", "categories", "products", "company"):
        assert re.search(rf"CREATE TABLE (?:public\.)?{tabela}\b", sql, re.I), tabela


def test_toda_tabela_referenciada_e_criada_em_migration_anterior():
    """FK para tabela criada depois quebra o `supabase db push` em banco limpo."""
    criada_em = {}
    for posicao, arquivo in enumerate(arquivos()):
        texto = arquivo.read_text(encoding="utf-8")
        for tabela in re.findall(r"CREATE TABLE (?:public\.)?(\w+)", texto, re.I):
            criada_em.setdefault(tabela.lower(), posicao)

    fora_de_ordem = []
    for posicao, arquivo in enumerate(arquivos()):
        texto = arquivo.read_text(encoding="utf-8")
        for alvo in re.findall(r"REFERENCES\s+(?:public\.)?(\w+)", texto, re.I):
            alvo = alvo.lower()
            origem = criada_em.get(alvo)
            if origem is None:
                fora_de_ordem.append(f"{arquivo.name} -> {alvo} (nunca criada)")
            elif origem > posicao:
                fora_de_ordem.append(
                    f"{arquivo.name} referencia {alvo}, criada só em "
                    f"{arquivos()[origem].name}"
                )

    assert fora_de_ordem == [], f"dependências fora de ordem: {fora_de_ordem}"


def test_tipo_unit_enum_criado_antes_de_ser_usado():
    sql = sql_completo()
    criacao = re.search(r"CREATE TYPE (?:public\.)?unit_enum\b", sql, re.I)
    uso = re.search(r"^\s*unit\s+(?:public\.)?unit_enum\b", sql, re.I | re.M)
    assert criacao and uso, "tipo unit_enum não encontrado"
    assert criacao.start() < uso.start()


def test_procedure_de_login_usa_colunas_que_existem():
    """pr_validate_login lê uma coluna que existe em access_register."""
    colunas = colunas_da_tabela("access_register")
    selecionada = re.search(
        r"SELECT\s+(\w+)\s+into\s+(?:STRICT\s+)?saved_hash",
        corpo_da_rotina("pr_validate_login"),
        re.I,
    ).group(1).lower()

    assert selecionada in colunas, (
        f"pr_validate_login faz SELECT {selecionada} em access_register, "
        f"mas a tabela só tem {colunas}"
    )


def test_login_exige_nome_unico():
    """O hash é resolvido por nome com SELECT ... INTO; sem UNIQUE é ambíguo."""
    linha_name = [
        l for l in corpo_da_tabela("access_register").splitlines()
        if l.strip().lower().startswith("name")
    ][0]
    assert "UNIQUE" in linha_name.upper(), (
        "access_register.name não é UNIQUE, mas o login busca o hash por nome"
    )


def test_login_falha_alto_quando_ha_nome_duplicado():
    """INTO STRICT: duplicata precisa estourar, não autenticar contra um hash qualquer."""
    corpo = corpo_da_rotina("pr_validate_login")
    assert re.search(r"into\s+STRICT\s+saved_hash", corpo, re.I), (
        "SELECT ... INTO sem STRICT mantém uma linha arbitrária em caso de duplicata"
    )


# -------------------------------------------- inserções multi-tenant

def test_insert_de_produto_preenche_todas_as_colunas_obrigatorias():
    """company_id é NOT NULL sem default desde que o schema virou multi-tenant."""
    for tabela, rotina in (("categories", "fn_create_categories"),
                           ("products", "fn_create_products")):
        colunas = set(colunas_da_tabela(tabela))
        obrigatorias = colunas_obrigatorias(tabela)

        insert = re.search(
            rf"INSERT INTO (?:public\.)?{tabela}\s*\((.*?)\)",
            corpo_da_rotina(rotina),
            re.S | re.I,
        )
        usadas = {c.strip().lower() for c in insert.group(1).split(",") if c.strip()}

        assert usadas <= colunas, f"{rotina}: colunas inexistentes {usadas - colunas}"
        assert obrigatorias <= usadas, (
            f"{rotina} não informa {obrigatorias - usadas} em {tabela}, "
            "que são NOT NULL sem default"
        )


# ------------------------------- permissão de escrita no catálogo (US01)
#
# ATENÇÃO À FONTE: tudo acima lê database/supabase/migrations (helpers
# `sql_completo` / `corpo_da_rotina`). Daqui para baixo a fonte é o SQL-FONTE
# em database/code, porque `fn_update_products` nasce lá e a migration
# correspondente ainda não foi gerada — quem espelha code/ para
# supabase/schemas/ e gera a migration é database/supabase_compiler.py, rodado
# por quem aplica o banco. Por isso o par de helpers separado abaixo: nenhum
# helper já existente muda de fonte.

CODE = RAIZ / "database" / "code"
CATALOGO_SQL = CODE / "procedures" / "05_catalog.sql"
TABELAS_CATALOGO_SQL = CODE / "tables" / "03_catalog.sql"
SEGURANCA_SQL = CODE / "policies" / "01_security.sql"

# Funções que gravam no catálogo. Uma função de escrita nova entra aqui e
# precisa passar nos mesmos testes de guard.
ESCRITAS_DO_CATALOGO = (
    "fn_create_categories",
    "fn_create_products",
    "fn_update_products",
    "fn_set_product_active",
)

DEFINICAO_DE_ROTINA = r"CREATE OR REPLACE (?:FUNCTION|PROCEDURE) (?:public\.)?(\w+)"


def sql_do_code():
    return "\n".join(
        f.read_text(encoding="utf-8") for f in sorted(CODE.rglob("*.sql"))
    )


def sem_comentarios(texto):
    """Remove comentários `--`: comparação de posição tem que ser código a código."""
    return re.sub(r"--[^\n]*", "", texto)


def corpo_da_rotina_no_code(nome):
    achado = re.search(
        rf"CREATE OR REPLACE (?:FUNCTION|PROCEDURE) (?:public\.)?{nome}\s*\(.*?\$\$;",
        sql_do_code(),
        re.S | re.I,
    )
    assert achado, f"rotina {nome} não encontrada em database/code"
    return achado.group(0)


def funcoes_com_grant():
    """Nomes do array v_names de policies/01_security.sql."""
    bloco = re.search(
        r"v_names\s+text\[\]\s*:=\s*ARRAY\[(.*?)\];",
        SEGURANCA_SQL.read_text(encoding="utf-8"),
        re.S,
    )
    assert bloco, "array v_names não encontrado em policies/01_security.sql"
    return {n.lower() for n in re.findall(r"'(\w+)'", sem_comentarios(bloco.group(1)))}


@pytest.mark.parametrize("rotina", ESCRITAS_DO_CATALOGO)
def test_escrita_de_catalogo_checa_papel_admin_ou_stock(rotina):
    """Nenhuma gravação de catálogo pode confiar só na camada de aplicação."""
    corpo = sem_comentarios(corpo_da_rotina_no_code(rotina))
    assert re.search(
        r"fn_has_role\s*\(.*?ARRAY\s*\[\s*'ADMIN'\s*,\s*'STOCK'\s*\]",
        corpo,
        re.S | re.I,
    ), f"{rotina} grava no catálogo sem checar fn_has_role ARRAY['ADMIN','STOCK']"


@pytest.mark.parametrize("rotina", ESCRITAS_DO_CATALOGO)
def test_guard_vem_antes_da_primeira_gravacao(rotina):
    """Chamada negada não altera dado: o guard precede o primeiro INSERT/UPDATE."""
    corpo = sem_comentarios(corpo_da_rotina_no_code(rotina))
    guard = re.search(r"fn_has_role\s*\(", corpo, re.I)
    gravacao = re.search(r"\b(?:INSERT\s+INTO|UPDATE)\s+(?:public\.)?\w+", corpo, re.I)
    assert guard, f"{rotina} não chama fn_has_role"
    assert gravacao, f"{rotina} não tem INSERT/UPDATE"
    assert guard.start() < gravacao.start(), (
        f"{rotina} grava antes de checar permissão: "
        f"{gravacao.group(0).strip()!r} aparece antes de fn_has_role"
    )


def test_fn_update_products_nao_recebe_company_id_do_chamador():
    """A empresa vem da linha do produto; recebê-la permitiria editar produto alheio."""
    assinatura = re.search(
        r"CREATE OR REPLACE FUNCTION (?:public\.)?fn_update_products\s*\((.*?)\)\s*RETURNS",
        sql_do_code(),
        re.S | re.I,
    )
    assert assinatura, "fn_update_products não encontrada em database/code"
    parametros = sem_comentarios(assinatura.group(1)).lower()
    assert "p_company_id" not in parametros, (
        "fn_update_products aceita p_company_id: o chamador poderia informar a "
        "empresa onde tem papel e editar produto de outra"
    )


def test_fn_update_products_so_atualiza_colunas_existentes():
    colunas = set(
        colunas_da_tabela("products", TABELAS_CATALOGO_SQL.read_text(encoding="utf-8"))
    )
    corpo = sem_comentarios(corpo_da_rotina_no_code("fn_update_products"))
    bloco = re.search(
        r"UPDATE\s+(?:public\.)?products\s+SET\s+(.*?)\s+WHERE\b", corpo, re.S | re.I
    )
    assert bloco, "fn_update_products não faz UPDATE em products"
    atribuidas = {m.group(1).lower() for m in re.finditer(r"(?m)^\s*(\w+)\s*=", bloco.group(1))}
    assert atribuidas, "nenhuma coluna atribuída no SET de fn_update_products"
    assert atribuidas <= colunas, (
        f"fn_update_products escreve em colunas inexistentes: {atribuidas - colunas}"
    )


def test_toda_funcao_do_v_names_existe_no_code():
    """v_names faz a migration falhar alto se a função sumir; o teste pega antes."""
    definidas = {n.lower() for n in re.findall(DEFINICAO_DE_ROTINA, sql_do_code(), re.I)}
    ausentes = funcoes_com_grant() - definidas
    assert not ausentes, (
        f"v_names concede EXECUTE a funções que não existem em database/code: "
        f"{sorted(ausentes)}"
    )


def test_toda_funcao_de_catalogo_esta_no_v_names():
    """Sem grant, a função fica inutilizável em runtime para app_backend."""
    do_catalogo = {
        n.lower()
        for n in re.findall(
            DEFINICAO_DE_ROTINA, CATALOGO_SQL.read_text(encoding="utf-8"), re.I
        )
    }
    sem_grant = do_catalogo - funcoes_com_grant()
    assert not sem_grant, (
        "funções de procedures/05_catalog.sql fora do v_names de "
        f"policies/01_security.sql: {sorted(sem_grant)}"
    )


def test_fn_update_products_e_security_definer_com_search_path_fixo():
    corpo = corpo_da_rotina_no_code("fn_update_products")
    assert re.search(r"SECURITY DEFINER", corpo, re.I), (
        "fn_update_products sem SECURITY DEFINER: app_backend não enxerga as "
        "tabelas, que só são lidas via policy"
    )
    assert re.search(r"SET\s+search_path\s*=\s*public", corpo, re.I), (
        "SECURITY DEFINER sem search_path fixo é vetor de hijack de schema"
    )
