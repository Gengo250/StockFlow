"""Testes do compilador de migrations (commit cc904e5)."""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPILER_PATH = ROOT / "database" / "supabase_compiler.py"


@pytest.fixture
def compiler():
    spec = importlib.util.spec_from_file_location("supabase_compiler", COMPILER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["supabase_compiler"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write(path: Path, content: str = "SELECT 1;"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_setup_cria_todas_as_pastas(compiler, workdir):
    compiler.setup_directories()
    for folder in compiler.EXECUTION_ORDER:
        assert (workdir / "archive" / folder).is_dir()
    assert (workdir / "supabase" / "migrations").is_dir()


def test_ordem_respeita_tables_antes_de_procedures(compiler, workdir):
    compiler.setup_directories()
    write(workdir / "archive" / "procedures" / "b.sql")
    write(workdir / "archive" / "tables" / "a.sql")
    write(workdir / "archive" / "policies" / "c.sql")

    ordem = [Path(f).parent.name for f in compiler.get_sql_files_in_order()]
    assert ordem == ["tables", "procedures", "policies"]


def test_timestamps_crescem_na_ordem_de_execucao(compiler, workdir):
    compiler.setup_directories()
    write(workdir / "archive" / "tables" / "a.sql")
    write(workdir / "archive" / "triggers" / "z.sql")

    compiler.process_and_create_migrations(compiler.get_sql_files_in_order())
    gerados = sorted(p.name for p in (workdir / "supabase" / "migrations").glob("*.sql"))
    assert gerados[0].endswith("_tables_a.sql")
    assert gerados[1].endswith("_triggers_z.sql")


def test_migration_gerada_preserva_o_conteudo_original(compiler, workdir):
    compiler.setup_directories()
    write(workdir / "archive" / "tables" / "a.sql", "CREATE TABLE t (id int);")

    compiler.process_and_create_migrations(compiler.get_sql_files_in_order())
    gerado = next((workdir / "supabase" / "migrations").glob("*.sql")).read_text()
    assert "CREATE TABLE t (id int);" in gerado
    assert "SOURCE: tables/a.sql" in gerado


def test_pasta_functions_tambem_e_compilada(compiler, workdir):
    """As migrations novas foram colocadas em archive/functions/."""
    compiler.setup_directories()
    write(workdir / "archive" / "functions" / "users" / "fn_x.sql")

    arquivos = compiler.get_sql_files_in_order()
    assert arquivos, (
        "archive/functions/** é ignorado: 'functions' não está em EXECUTION_ORDER, "
        "então as migrations de usuários/estoque nunca são geradas pelo compilador"
    )


def test_arquivo_compilado_sai_da_fila_apos_arquivamento(compiler, workdir):
    """Depois de compilar+arquivar, o fonte não pode ser recompilado de novo."""
    compiler.setup_directories()
    write(workdir / "archive" / "tables" / "a.sql", "CREATE TABLE t (id int);")

    arquivos = compiler.get_sql_files_in_order()
    compiler.process_and_create_migrations(arquivos)
    compiler.archive_files(arquivos)

    assert compiler.get_sql_files_in_order() == [], (
        "SOURCE_DIR e ARCHIVE_DIR são ambos 'archive': archive_files() não move "
        "nada e toda execução recompila os mesmos arquivos"
    )
