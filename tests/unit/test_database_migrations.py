"""Validação estática das migrations SQL (commits cc904e5 e 66aff01).

Usa o parser oficial do PostgreSQL (libpg_query, via pglast) para garantir que
todo arquivo .sql versionado é sintaticamente válido, e checa a consistência
entre as cópias duplicadas da mesma migration.
"""

from pathlib import Path

import pytest
from pglast import parser

ROOT = Path(__file__).resolve().parents[2]

# Projeto Supabase canônico (é o único diretório com config.toml).
CANONICAL = ROOT / "database" / "supabase" / "migrations"
# Cópias espelhadas criadas no commit 66aff01.
MIRRORS = (
    ROOT / "supabase" / "migrations",
    ROOT / "database" / "archive" / "functions",
    ROOT / "supabase" / "migrations" / "functions",
)


def all_sql_files():
    return sorted(
        p
        for p in ROOT.rglob("*.sql")
        if ".git" not in p.parts and ".venv" not in p.parts
    )


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


@pytest.mark.parametrize("sql_file", all_sql_files(), ids=rel)
def test_sql_e_sintaticamente_valido(sql_file):
    text = sql_file.read_text(encoding="utf-8")
    if not text.strip():
        pytest.skip("arquivo vazio (placeholder)")
    try:
        parser.parse_sql(text)
    except Exception as exc:  # pglast.parser.ParseError
        pytest.fail(f"SQL inválido em {rel(sql_file)}: {exc}")


def test_config_toml_existe_apenas_no_projeto_canonico():
    assert (CANONICAL.parent / "config.toml").is_file()
    assert not (ROOT / "supabase" / "config.toml").exists(), (
        "existem dois projetos Supabase; defina um único diretório canônico"
    )


def test_migrations_nao_ficam_em_subpastas_ignoradas_pelo_cli():
    """O Supabase CLI só aplica .sql na raiz de <project>/migrations."""
    escondidas = [
        rel(p)
        for base in (CANONICAL, ROOT / "supabase" / "migrations")
        if base.is_dir()
        for p in base.rglob("*.sql")
        if p.parent != base
    ]
    assert escondidas == [], (
        "estes arquivos nunca serão aplicados pelo 'supabase db push': "
        f"{escondidas}"
    )


def test_copias_duplicadas_tem_o_mesmo_conteudo():
    divergentes = []
    for canonical_file in sorted(CANONICAL.glob("*.sql")):
        for mirror in MIRRORS:
            for copy in mirror.rglob(canonical_file.name):
                a = canonical_file.read_text(encoding="utf-8").strip()
                b = copy.read_text(encoding="utf-8").strip()
                if a != b:
                    divergentes.append(f"{rel(canonical_file)} != {rel(copy)}")
    assert divergentes == [], "cópias da mesma migration divergiram:\n" + "\n".join(
        divergentes
    )


def test_dependencias_sao_criadas_antes_do_uso_no_projeto_canonico():
    """Migrations rodam em ordem de timestamp; o alvo precisa existir antes."""
    criados: set[str] = set()
    problemas = []

    dependencias = {
        "20261001210403_02_stock_min_config.sql": ["products"],
        "20261001222418_vw_stock-situation.sql": ["products", "product_stock"],
        "20261001220553_fn_is_admin.sql": ["company_users"],
        "20261001220632_fn_login_check.sql": ["user_accounts", "company_users"],
        "20261001222047_fn_set_min_stock.sql": ["products", "product_stock"],
    }

    for migration in sorted(CANONICAL.glob("*.sql")):
        text = migration.read_text(encoding="utf-8").lower()
        for required in dependencias.get(migration.name, []):
            if required not in criados:
                problemas.append(
                    f"{migration.name} usa '{required}' antes de ela ser criada"
                )
        for line in text.splitlines():
            if "create table" in line:
                criados.add(line.split("create table")[1].strip(" ;(").replace("public.", ""))

    assert problemas == [], "\n".join(problemas)


def test_existe_apenas_uma_arvore_de_migrations():
    arvores = sorted(
        rel(p)
        for p in ROOT.rglob("migrations")
        if p.is_dir() and ".git" not in p.parts and ".venv" not in p.parts
        and any(p.glob("*.sql"))
    )
    assert arvores == [rel(CANONICAL)], (
        f"migrations duplicadas em múltiplos diretórios: {arvores}"
    )


def test_arvore_orfa_de_supabase_nao_cria_a_tabela_products():
    """A cópia em supabase/migrations referencia products(id) sem criá-la."""
    orfa = ROOT / "supabase" / "migrations"
    if not orfa.is_dir():
        pytest.skip("árvore órfã já removida")
    corpo = "\n".join(p.read_text(encoding="utf-8") for p in orfa.glob("*.sql")).lower()
    referencia_products = "references public.products" in corpo
    cria_products = "create table public.products" in corpo or "create table products" in corpo
    assert not (referencia_products and not cria_products), (
        "supabase/migrations referencia public.products mas nunca a cria — "
        "um 'db push' nesse diretório falharia"
    )


def test_tabelas_sensiveis_tem_rls_habilitado():
    """No Supabase as tabelas ficam expostas via PostgREST sem RLS."""
    corpo = "\n".join(
        p.read_text(encoding="utf-8") for p in CANONICAL.glob("*.sql")
    ).lower()
    sem_rls = [
        tabela
        for tabela in ("user_accounts", "company_users", "company", "product_stock", "products")
        if f"alter table public.{tabela} enable row level security" not in corpo
        and f"alter table {tabela} enable row level security" not in corpo
    ]
    assert sem_rls == [], (
        f"tabelas sem RLS (leitura/escrita abertas pela chave publishable): {sem_rls}"
    )


def test_funcoes_de_gestao_nao_dependem_de_variavel_de_sessao_nao_configurada():
    """fn_current_user_id lê app.user_id; nada no projeto define esse GUC."""
    usa_guc = "app.user_id" in (
        CANONICAL / "20261001220550_fn_current_user_id.sql"
    ).read_text(encoding="utf-8")
    if not usa_guc:
        pytest.skip("função não usa mais GUC de sessão")

    define_guc = any(
        "set_config('app.user_id'" in p.read_text(encoding="utf-8").lower()
        or "set app.user_id" in p.read_text(encoding="utf-8").lower()
        for p in [*CANONICAL.glob("*.sql"), *(ROOT / "src").rglob("*.py")]
    )
    assert define_guc, (
        "fn_current_user_id() sempre retorna NULL: nenhuma migration nem o código "
        "Python define 'app.user_id', então fn_create/update/toggle_company_user "
        "sempre lançam 'Apenas administradores...'"
    )
