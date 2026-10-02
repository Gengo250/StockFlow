"""Commit cc904e5 - comportamento do database/supabase_compiler.py."""

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
COMPILER = RAIZ / "database" / "supabase_compiler.py"


def carregar_compiler():
    spec = importlib.util.spec_from_file_location("supabase_compiler", COMPILER)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Roda o compiler num diretório descartável, nunca no projeto real."""
    monkeypatch.chdir(tmp_path)
    modulo = carregar_compiler()
    modulo.setup_directories()
    return modulo, tmp_path


def test_setup_cria_todas_as_pastas(sandbox):
    modulo, raiz = sandbox
    for pasta in modulo.EXECUTION_ORDER:
        assert (raiz / "archive" / pasta).is_dir()
    assert (raiz / "supabase" / "migrations").is_dir()


def test_arquivos_sao_lidos_na_ordem_de_execucao(sandbox):
    modulo, raiz = sandbox
    (raiz / "archive" / "policies" / "a.sql").write_text("-- policy")
    (raiz / "archive" / "tables" / "a.sql").write_text("-- table")
    (raiz / "archive" / "procedures" / "a.sql").write_text("-- proc")

    pastas = [Path(f).parent.name for f in modulo.get_sql_files_in_order()]
    assert pastas == ["tables", "procedures", "policies"]


def test_migrations_recebem_timestamps_crescentes(sandbox):
    modulo, raiz = sandbox
    (raiz / "archive" / "tables" / "a.sql").write_text("CREATE TABLE a ();")
    (raiz / "archive" / "tables" / "b.sql").write_text("CREATE TABLE b ();")

    modulo.process_and_create_migrations(modulo.get_sql_files_in_order())

    nomes = sorted(p.name for p in (raiz / "supabase" / "migrations").glob("*.sql"))
    assert len(nomes) == 2
    assert [n[:14] for n in nomes] == sorted(n[:14] for n in nomes)


def test_migration_preserva_o_conteudo_do_sql(sandbox):
    modulo, raiz = sandbox
    (raiz / "archive" / "tables" / "a.sql").write_text("CREATE TABLE a (id INT);")
    modulo.process_and_create_migrations(modulo.get_sql_files_in_order())

    gerado = next((raiz / "supabase" / "migrations").glob("*.sql")).read_text()
    assert "CREATE TABLE a (id INT);" in gerado
    assert "SOURCE: tables/a.sql" in gerado


def test_archive_realmente_move_os_arquivos_compilados(sandbox):
    """Depois de compilar, o .sql cru não deve ser recompilado na próxima rodada."""
    modulo, raiz = sandbox
    (raiz / "archive" / "tables" / "a.sql").write_text("CREATE TABLE a ();")

    arquivos = modulo.get_sql_files_in_order()
    modulo.process_and_create_migrations(arquivos)
    modulo.archive_files(arquivos)

    assert modulo.get_sql_files_in_order() == [], (
        "SOURCE_DIR e ARCHIVE_DIR são o mesmo diretório: nada é arquivado"
    )


def test_rodar_duas_vezes_nao_duplica_migrations(sandbox, monkeypatch):
    """Duas execuções em momentos diferentes não podem gerar a mesma tabela 2x."""
    modulo, raiz = sandbox
    (raiz / "archive" / "tables" / "a.sql").write_text("CREATE TABLE a ();")

    momentos = iter([
        datetime(2026, 10, 1, 10, 0, 0),
        datetime(2026, 10, 1, 11, 0, 0),
    ])

    class RelogioFixo(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(momentos)

    monkeypatch.setattr(modulo, "datetime", RelogioFixo)

    for _ in range(2):
        arquivos = modulo.get_sql_files_in_order()
        modulo.process_and_create_migrations(arquivos)
        modulo.archive_files(arquivos)

    gerados = list((raiz / "supabase" / "migrations").glob("*_tables_a.sql"))
    assert len(gerados) == 1, (
        f"a mesma tabela virou {len(gerados)} migrations: "
        "o segundo push tentaria CREATE TABLE duas vezes"
    )
