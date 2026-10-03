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

PADROES = (
    (r"CREATE TABLE\s+(?:public\.)?(\w+)", "table"),
    (r"CREATE TYPE\s+(?:public\.)?(\w+)", "type"),
    (r"CREATE (?:OR REPLACE )?VIEW\s+(?:public\.)?(\w+)", "view"),
    (r"CREATE (?:OR REPLACE )?FUNCTION\s+(?:public\.)?(\w+)", "function"),
    (r"CREATE (?:OR REPLACE )?PROCEDURE\s+(?:public\.)?(\w+)", "procedure"),
    (r"CREATE TRIGGER\s+(\w+)", "trigger"),
    (r"CREATE INDEX\s+(\w+)", "index"),
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
        texto = arquivo.read_text(encoding="utf-8")
        for padrao, tipo in PADROES:
            for nome in re.findall(padrao, texto, re.I):
                achados.add((tipo, nome.lower()))
    return achados


def arquivos_na_ordem():
    ordenados = []
    for pasta in ORDEM:
        ordenados += sorted((CODE / pasta).glob("*.sql"))
    return ordenados


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
