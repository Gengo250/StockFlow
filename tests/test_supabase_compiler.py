"""Comportamento do database/supabase_compiler.py.

O compilador artesanal foi substituído por um wrapper sobre
`supabase db schema declarative sync`: ele espelha `code/` em
`supabase/schemas/` e deixa a geração da migration para a CLI. Os testes
cobrem a parte que roda sem Docker e sem a CLI — o espelhamento e a leitura
do .env — e guardam a regressão que motivou a reescrita: origem e destino
apontando para a mesma pasta.
"""

import importlib.util
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
    modulo = carregar_compiler()  # o módulo faz chdir para database/ ao importar
    monkeypatch.chdir(tmp_path)

    for pasta in modulo.EXECUTION_ORDER:
        (tmp_path / "code" / pasta).mkdir(parents=True, exist_ok=True)
    (tmp_path / "supabase" / "migrations").mkdir(parents=True, exist_ok=True)

    return modulo, tmp_path


# ----------------------------------------------- a regressão que motivou tudo

def test_origem_e_destino_sao_pastas_diferentes():
    """SOURCE_DIR == ARCHIVE_DIR fazia o arquivo bruto nunca sair do caminho
    de compilação, e a execução seguinte gerava uma segunda migration para a
    mesma tabela."""
    modulo = carregar_compiler()
    assert Path(modulo.SOURCE_DIR) != Path(modulo.SCHEMAS_DIR)
    assert Path(modulo.SOURCE_DIR) != Path(modulo.MIGRATIONS_DIR)


def test_compilador_nao_gera_migration_por_conta_propria():
    """A numeração passou a ser responsabilidade da CLI do Supabase."""
    fonte = COMPILER.read_text(encoding="utf-8")
    assert "strftime" not in fonte
    assert "timedelta" not in fonte


# --------------------------------------------------------- espelhamento

def test_sync_espelha_code_em_schemas(sandbox):
    modulo, raiz = sandbox
    (raiz / "code" / "tables" / "a.sql").write_text("-- tabela a", encoding="utf-8")
    (raiz / "code" / "procedures" / "b.sql").write_text("-- proc b", encoding="utf-8")

    modulo.sync_schemas()

    assert (raiz / "supabase" / "schemas" / "tables" / "a.sql").read_text(encoding="utf-8") == "-- tabela a"
    assert (raiz / "supabase" / "schemas" / "procedures" / "b.sql").read_text(encoding="utf-8") == "-- proc b"


def test_sync_preserva_o_conteudo_do_sql(sandbox):
    modulo, raiz = sandbox
    conteudo = "CREATE TABLE exemplo (\n  id UUID PRIMARY KEY\n);\n"
    (raiz / "code" / "tables" / "exemplo.sql").write_text(conteudo, encoding="utf-8")

    modulo.sync_schemas()

    espelhado = raiz / "supabase" / "schemas" / "tables" / "exemplo.sql"
    assert espelhado.read_text(encoding="utf-8") == conteudo


def test_rodar_duas_vezes_nao_duplica_nada(sandbox):
    modulo, raiz = sandbox
    (raiz / "code" / "tables" / "a.sql").write_text("-- tabela a", encoding="utf-8")

    modulo.sync_schemas()
    modulo.sync_schemas()

    espelhados = sorted((raiz / "supabase" / "schemas").rglob("*.sql"))
    assert [p.name for p in espelhados] == ["a.sql"]


def test_arquivo_removido_de_code_some_de_schemas(sandbox):
    modulo, raiz = sandbox
    (raiz / "code" / "tables" / "a.sql").write_text("-- tabela a", encoding="utf-8")
    modulo.sync_schemas()

    (raiz / "code" / "tables" / "a.sql").unlink()
    modulo.sync_schemas()

    assert not (raiz / "supabase" / "schemas" / "tables" / "a.sql").exists()


def test_sync_cria_uma_pasta_por_etapa_da_ordem(sandbox):
    modulo, raiz = sandbox
    modulo.sync_schemas()

    for pasta in modulo.EXECUTION_ORDER:
        assert (raiz / "supabase" / "schemas" / pasta).is_dir()


# ---------------------------------------------------------- list_migrations

def test_list_migrations_enxerga_apenas_sql(sandbox):
    modulo, raiz = sandbox
    migrations = raiz / "supabase" / "migrations"
    (migrations / "20261001000000_a.sql").write_text("-- a", encoding="utf-8")
    (migrations / "README.md").write_text("doc", encoding="utf-8")

    nomes = {Path(p).name for p in modulo.list_migrations()}
    assert nomes == {"20261001000000_a.sql"}


# ------------------------------------------------------------- load_env

def test_load_env_le_pares_e_ignora_comentarios(tmp_path, monkeypatch):
    modulo = carregar_compiler()
    env = tmp_path / ".env"
    env.write_text(
        "# comentário\n"
        "\n"
        'SUPABASE_PROJECT_REF="abc123"\n'
        "OUTRO=valor simples\n"
        "LINHA_SEM_IGUAL\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SUPABASE_PROJECT_REF", raising=False)
    monkeypatch.delenv("OUTRO", raising=False)

    modulo.load_env(str(env))

    import os

    assert os.environ["SUPABASE_PROJECT_REF"] == "abc123"
    assert os.environ["OUTRO"] == "valor simples"


def test_load_env_nao_sobrescreve_variavel_ja_definida(tmp_path, monkeypatch):
    modulo = carregar_compiler()
    env = tmp_path / ".env"
    env.write_text("SUPABASE_PROJECT_REF=do-arquivo\n", encoding="utf-8")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", "do-ambiente")

    modulo.load_env(str(env))

    import os

    assert os.environ["SUPABASE_PROJECT_REF"] == "do-ambiente"
