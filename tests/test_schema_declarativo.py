"""Coerência da fonte declarativa em database/code.

O fluxo declarativo do Supabase aplica os arquivos de `code/` (espelhados em
`supabase/schemas/`) na ordem de `schema_paths` e diffa o resultado contra o
banco. Dois riscos justificam estes testes:

1. Se `code/` não cobrir tudo que as migrations criam, o primeiro
   `declarative sync` propõe derrubar o que ficou de fora.
2. Se um arquivo referenciar algo definido só mais adiante na ordem, a
   aplicação do schema quebra — foi assim que `tables_products` acabou
   referenciando `company` antes de ela existir.

Não há Postgres neste ambiente, então a verificação é estática.
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CODE = RAIZ / "database" / "code"
SCHEMAS = RAIZ / "database" / "supabase" / "schemas"
MIGRATIONS = RAIZ / "database" / "supabase" / "migrations"

# Mesma ordem de supabase/config.toml e de EXECUTION_ORDER no compilador.
ORDEM = ["tables", "procedures", "views", "triggers", "policies"]

# `IF NOT EXISTS` é opcional em toda criação. Migration que roda sobre um banco
# que já tem parte do objeto precisa da forma longa, e sem tolerá-la aqui o
# regex captura o literal "IF" como NOME do objeto. O estrago é duplo e
# silencioso: `('table', 'if')` aparece como objeto sem fonte declarativa, e o
# objeto de verdade some da comparação dos dois lados.
#
# `UNIQUE` entra pelo mesmo motivo: `CREATE UNIQUE INDEX` não casava com nada,
# então índice único declarado só nas migrations passava despercebido.
SE_NAO_EXISTIR = r"(?:IF NOT EXISTS\s+)?"

PADROES = (
    (rf"CREATE TABLE\s+{SE_NAO_EXISTIR}(?:public\.)?(\w+)", "table"),
    (rf"CREATE TYPE\s+{SE_NAO_EXISTIR}(?:public\.)?(\w+)", "type"),
    (rf"CREATE (?:OR REPLACE )?VIEW\s+{SE_NAO_EXISTIR}(?:public\.)?(\w+)", "view"),
    (r"CREATE (?:OR REPLACE )?FUNCTION\s+(?:public\.)?(\w+)", "function"),
    (r"CREATE (?:OR REPLACE )?PROCEDURE\s+(?:public\.)?(\w+)", "procedure"),
    (rf"CREATE TRIGGER\s+{SE_NAO_EXISTIR}(\w+)", "trigger"),
    (rf"CREATE (?:UNIQUE )?INDEX\s+{SE_NAO_EXISTIR}(\w+)", "index"),
)

# Funções nativas do Postgres que nunca precisam ser declaradas.
NATIVAS = {
    "jsonb_array_elements", "jsonb_typeof", "gen_random_uuid", "now", "crypt",
    "lower", "btrim", "left", "length", "coalesce", "nullif", "count",
    "current_setting", "exists",
}


def objetos(arquivos):
    achados = set()
    for arquivo in arquivos:
        # Comentário não cria objeto: um `-- ... CREATE TABLE de 03_catalog`
        # explicando onde a coluna nasce virava a "tabela de".
        texto = re.sub(r"--[^\n]*", "", arquivo.read_text(encoding="utf-8"))
        eventos = []
        for padrao, tipo in PADROES:
            for match in re.finditer(padrao, texto, re.I):
                eventos.append((match.start(), "create", tipo, match.group(1).lower()))
        for match in re.finditer(
            r"DROP (TABLE|TYPE|VIEW|FUNCTION|PROCEDURE|TRIGGER|INDEX)\s+"
            r"(?:IF EXISTS\s+)?(?:public\.)?(\w+)", texto, re.I
        ):
            eventos.append((match.start(), "drop", match.group(1).lower(), match.group(2).lower()))
        # Inventário estático por nome. A execução em PostgreSQL é quem
        # verifica assinaturas, dependências e efeitos de CASCADE.
        for _, acao, tipo, nome in sorted(eventos):
            if acao == "create":
                achados.add((tipo, nome))
            else:
                achados.discard((tipo, nome))
    return achados


def arquivos_na_ordem():
    ordenados = []
    for pasta in ORDEM:
        ordenados += sorted((CODE / pasta).glob("*.sql"))
    return ordenados


def test_inventario_respeita_remocao_e_recriacao_de_objetos(tmp_path):
    antigo = tmp_path / "01.sql"
    novo = tmp_path / "02.sql"
    antigo.write_text("CREATE TABLE public.antiga(id int); CREATE INDEX idx_old ON antiga(id);")
    novo.write_text("DROP INDEX IF EXISTS public.idx_old; DROP TABLE public.antiga; "
                    "CREATE TABLE public.atual(id int); DROP TABLE public.atual; "
                    "CREATE TABLE public.atual(id int);")
    assert objetos([antigo, novo]) == {("table", "atual")}


def test_code_cobre_todos_os_objetos_das_migrations():
    """Objeto que existe só nas migrations seria proposto para remoção."""
    das_migrations = objetos(sorted(MIGRATIONS.glob("*.sql")))
    do_code = objetos(sorted(CODE.rglob("*.sql")))

    faltando = sorted(das_migrations - do_code)
    assert faltando == [], f"objetos sem fonte declarativa em code/: {faltando}"


def test_code_nao_inventa_objetos_fora_das_migrations():
    das_migrations = objetos(sorted(MIGRATIONS.glob("*.sql")))
    do_code = objetos(sorted(CODE.rglob("*.sql")))

    sobrando = sorted(do_code - das_migrations)
    assert sobrando == [], f"objetos em code/ sem migration correspondente: {sobrando}"


def test_schemas_e_espelho_exato_de_code():
    """sync_schemas() copia code/ para supabase/schemas/; divergência aqui
    significa que alguém editou o espelho em vez da fonte."""
    de_code = {p.relative_to(CODE): p.read_text(encoding="utf-8") for p in CODE.rglob("*.sql")}
    de_schemas = {p.relative_to(SCHEMAS): p.read_text(encoding="utf-8") for p in SCHEMAS.rglob("*.sql")}
    assert de_code == de_schemas


def test_dependencias_resolvem_na_ordem_do_schema_paths():
    """Tudo que o Postgres resolve na criação precisa já existir.

    Corpo de plpgsql é ignorado de propósito: o Postgres não valida esse corpo
    na criação, só o de LANGUAGE sql e o de views.
    """
    definidos = set(NATIVAS)
    problemas = []

    for arquivo in arquivos_na_ordem():
        texto = arquivo.read_text(encoding="utf-8")
        exigidos = set()

        for alvo in re.findall(r"REFERENCES\s+(?:public\.)?(\w+)", texto, re.I):
            exigidos.add(alvo.lower())

        for tipo in re.findall(
            r"\b(?:public\.)?(\w*_enum|user_role|stock_state|company_stock_state)\b", texto, re.I
        ):
            exigidos.add(tipo.lower())

        for m in re.finditer(
            r"(CREATE OR REPLACE (?:FUNCTION|VIEW).*?)(?=CREATE OR REPLACE|\Z)", texto, re.S | re.I
        ):
            trecho = m.group(1)
            if re.search(r"LANGUAGE\s+plpgsql", trecho, re.I):
                continue
            for ref in re.findall(r"\b(?:FROM|JOIN)\s+(?:public\.)?(\w+)", trecho, re.I):
                exigidos.add(ref.lower())
            for ref in re.findall(r"\bpublic\.(\w+)\s*\(", trecho, re.I):
                exigidos.add(ref.lower())

        for tabela in re.findall(
            r"CREATE TRIGGER\s+\w+\s+\w+(?:\s+OR\s+\w+)*\s+ON\s+(?:public\.)?(\w+)", texto, re.I
        ):
            exigidos.add(tabela.lower())
        for fn in re.findall(r"EXECUTE FUNCTION\s+(?:public\.)?(\w+)", texto, re.I):
            exigidos.add(fn.lower())

        for padrao, _ in PADROES:
            for nome in re.findall(padrao, texto, re.I):
                definidos.add(nome.lower())

        faltando = sorted(e for e in exigidos if e not in definidos)
        if faltando:
            problemas.append(f"{arquivo.relative_to(CODE)} usa {faltando} antes de existir")

    assert problemas == [], f"dependências fora de ordem: {problemas}"


def test_ordem_do_compilador_bate_com_o_config():
    """vw_stock_situation chama fn_stock_state, então procedures vem antes de views."""
    config = (RAIZ / "database" / "supabase" / "config.toml").read_text(encoding="utf-8")
    pastas = re.findall(r'"\./schemas/(\w+)/\*\.sql"', config)
    assert pastas == ORDEM, f"schema_paths em ordem inesperada: {pastas}"

    compilador = (RAIZ / "database" / "supabase_compiler.py").read_text(encoding="utf-8")
    declarada = re.search(r"EXECUTION_ORDER = \[(.*?)\]", compilador, re.S).group(1)
    assert re.findall(r'"(\w+)"', declarada) == ORDEM


# `supabase db push` manda cada comando da migration separadamente, em
# autocommit: não existe transação envolvendo o arquivo. Quem precisa de uma
# tem que abrir a sua. Foi exatamente isso que derrubou a US09/US10 no remoto
# ("LOCK TABLE can only be used in transaction blocks", SQLSTATE 25P01), e a
# verificação local não pegou porque ela aplicava cada arquivo já dentro de
# uma transação.
EXIGEM_TRANSACAO = {
    "LOCK TABLE": r"\bLOCK\s+TABLE\b",
    "SET CONSTRAINTS": r"\bSET\s+CONSTRAINTS\b",
}

# O avesso: dentro de uma transação o PostgreSQL recusa estes. Uma migration
# que abre BEGIN não pode misturá-los.
PROIBIDOS_EM_TRANSACAO = {
    "CONCURRENTLY": r"\bCONCURRENTLY\b",
    "VACUUM": r"\bVACUUM\b",
    "ALTER SYSTEM": r"\bALTER\s+SYSTEM\b",
    "CREATE DATABASE": r"\bCREATE\s+DATABASE\b",
    "DROP DATABASE": r"\bDROP\s+DATABASE\b",
    "CREATE TABLESPACE": r"\bCREATE\s+TABLESPACE\b",
}


def fora_de_corpo(arquivo):
    """Texto sem comentário e sem corpo `$$...$$`.

    Dentro de função o comando já roda numa transação, então um LOCK ali não
    diz nada sobre como o arquivo é aplicado."""
    texto = re.sub(r"--[^\n]*", "", arquivo.read_text(encoding="utf-8"))
    return re.sub(r"\$(\w*)\$.*?\$\1\$", " ", texto, flags=re.S)


def abre_transacao(texto):
    return bool(re.match(r"\s*BEGIN\s*;", texto, re.I)) and bool(
        re.search(r"\bCOMMIT\s*;\s*\Z", texto, re.I)
    )


def test_migration_que_exige_transacao_abre_a_propria():
    faltando = []
    for arquivo in sorted(MIGRATIONS.glob("*.sql")):
        texto = fora_de_corpo(arquivo)
        usados = [n for n, p in EXIGEM_TRANSACAO.items() if re.search(p, texto, re.I)]
        if usados and not abre_transacao(texto):
            faltando.append(f"{arquivo.name} usa {usados} sem BEGIN;/COMMIT; próprios")

    assert faltando == [], f"recusadas por `db push` com 25P01: {faltando}"


def test_migration_em_transacao_nao_usa_comando_proibido():
    conflitos = []
    for arquivo in sorted(MIGRATIONS.glob("*.sql")):
        texto = fora_de_corpo(arquivo)
        if not abre_transacao(texto):
            continue
        achados = [n for n, p in PROIBIDOS_EM_TRANSACAO.items() if re.search(p, texto, re.I)]
        if achados:
            conflitos.append(f"{arquivo.name} abre transação e usa {achados}")

    assert conflitos == [], f"comandos que não rodam dentro de transação: {conflitos}"
