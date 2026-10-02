"""Commit cc904e5 - migrations geradas pelo database/supabase_compiler.py.

Não há Postgres, psql nem Supabase CLI neste ambiente, então estes testes
validam estaticamente a ordem das migrations e a coerência entre as colunas
declaradas nas tabelas e as colunas usadas pelas procedures.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
MIGRATIONS = RAIZ / "database" / "supabase" / "migrations"
ORDEM = ["tables", "views", "procedures", "triggers", "policies"]


def arquivos():
    return sorted(MIGRATIONS.glob("*.sql"))


def sql_completo():
    return "\n".join(f.read_text(encoding="utf-8") for f in arquivos())


def colunas_da_tabela(nome):
    corpo = re.search(
        rf"CREATE TABLE {nome}\s*\((.*?)\n\);",
        sql_completo(),
        re.S | re.I,
    )
    assert corpo, f"tabela {nome} não encontrada"
    encontradas = []
    for linha in corpo.group(1).splitlines():
        linha = linha.strip().rstrip(",")
        if not linha or linha.upper().startswith(("CHECK", "CONSTRAINT", "PRIMARY KEY", "FOREIGN KEY")):
            continue
        encontradas.append(linha.split()[0].lower())
    return encontradas


# ------------------------------------------------------ nomes e ordem

def test_todas_as_migrations_tem_timestamp_valido():
    for arquivo in arquivos():
        assert re.match(r"^\d{14}_[a-z]+_[a-z_]+\.sql$", arquivo.name), arquivo.name


def test_timestamps_sao_crescentes_e_unicos():
    stamps = [a.name[:14] for a in arquivos()]
    assert stamps == sorted(stamps)
    assert len(stamps) == len(set(stamps))


def test_ordem_de_execucao_respeita_tables_antes_de_procedures():
    categorias = [a.name[15:].split("_")[0] for a in arquivos()]
    indices = [ORDEM.index(c) for c in categorias]
    assert indices == sorted(indices), f"ordem incorreta: {categorias}"


def test_nenhuma_migration_duplicada_para_a_mesma_origem():
    origens = [a.name[15:] for a in arquivos()]
    assert len(origens) == len(set(origens)), f"origens repetidas: {origens}"


# ------------------------------------------------- coerência do schema

def test_tabelas_esperadas_existem():
    sql = sql_completo()
    for tabela in ("access_register", "register", "categories", "products"):
        assert re.search(rf"CREATE TABLE {tabela}\b", sql, re.I), tabela


def test_foreign_keys_apontam_para_tabelas_criadas_antes():
    sql = sql_completo()
    posicoes = {
        t: sql.upper().index(f"CREATE TABLE {t.upper()}")
        for t in ("access_register", "register", "categories", "products")
    }
    assert posicoes["access_register"] < posicoes["register"]
    assert posicoes["categories"] < posicoes["products"]


def test_tipo_unit_enum_criado_antes_de_ser_usado():
    sql = sql_completo()
    assert sql.upper().index("CREATE TYPE UNIT_ENUM") < sql.upper().index("UNIT UNIT_ENUM")


def test_procedure_validate_login_usa_colunas_que_existem():
    """validate_login lê uma coluna da tabela access_register."""
    colunas = colunas_da_tabela("access_register")
    corpo = re.search(
        r"CREATE OR REPLACE PROCEDURE validate_login.*?\$\$;",
        sql_completo(),
        re.S | re.I,
    )
    assert corpo, "procedure validate_login não encontrada"

    selecionada = re.search(
        r"SELECT\s+(\w+)\s+into\s+saved_hash",
        corpo.group(0),
        re.I,
    ).group(1).lower()

    assert selecionada in colunas, (
        f"validate_login faz SELECT {selecionada} em access_register, "
        f"mas a tabela só tem {colunas}"
    )


def test_create_products_usa_colunas_que_existem():
    colunas = set(colunas_da_tabela("products"))
    corpo = re.search(
        r"CREATE OR REPLACE FUNCTION create_products.*?\$\$;",
        sql_completo(),
        re.S | re.I,
    )
    insert = re.search(r"INSERT INTO products\s*\((.*?)\)", corpo.group(0), re.S | re.I)
    usadas = {c.strip().lower() for c in insert.group(1).split(",") if c.strip()}
    assert usadas <= colunas, f"colunas inexistentes: {usadas - colunas}"


def test_login_exige_nome_unico():
    """validate_login usa SELECT ... INTO por nome; sem UNIQUE o retorno é ambíguo."""
    corpo = re.search(
        r"CREATE TABLE access_register\s*\((.*?)\n\);",
        sql_completo(),
        re.S | re.I,
    ).group(1)
    linha_name = [l for l in corpo.splitlines() if l.strip().lower().startswith("name")][0]
    assert "UNIQUE" in linha_name.upper(), (
        "access_register.name não é UNIQUE, mas validate_login busca o hash por nome"
    )
