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

RAIZ = Path(__file__).resolve().parents[1]
MIGRATIONS = RAIZ / "database" / "supabase" / "migrations"


def arquivos():
    return sorted(MIGRATIONS.glob("*.sql"))


def sql_completo():
    return "\n".join(f.read_text(encoding="utf-8") for f in arquivos())


def corpo_da_tabela(nome):
    """Bloco entre parênteses do CREATE TABLE, com ou sem prefixo de schema."""
    achado = re.search(
        rf"CREATE TABLE (?:public\.)?{nome}\s*\((.*?)\n\);",
        sql_completo(),
        re.S | re.I,
    )
    assert achado, f"tabela {nome} não encontrada"
    return achado.group(1)


IGNORAR_NA_TABELA = (
    "CHECK", "CONSTRAINT", "PRIMARY KEY", "FOREIGN KEY",
    "UNIQUE", "REFERENCES", "ON ",
)


def linhas_de_coluna(nome):
    for linha in corpo_da_tabela(nome).splitlines():
        linha = linha.strip().rstrip(",")
        if not linha or linha.upper().startswith(IGNORAR_NA_TABELA):
            continue
        yield linha


def colunas_da_tabela(nome):
    return [linha.split()[0].lower() for linha in linhas_de_coluna(nome)]


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
