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


def test_fn_toggle_company_user_atualiza_vinculo_sem_excluir_identidade():
    """US06 desativa o vínculo correto sem apagar a conta nem o histórico."""
    corpo = sem_comentarios(corpo_da_rotina_no_code("fn_toggle_company_user"))
    guard = re.search(r"fn_is_admin\s*\(", corpo, re.I)
    atualizacao = re.search(
        r"UPDATE\s+public\.company_users\s+SET\s+active\s*=\s*p_active"
        r"\s+WHERE\s+company_id\s*=\s*p_company_id"
        r"\s+AND\s+user_account_id\s*=\s*p_user_id",
        corpo,
        re.I,
    )

    assert guard and atualizacao
    assert guard.start() < atualizacao.start()
    assert not re.search(r"\bDELETE\b", corpo, re.I)


def test_login_e_empresa_atual_exigem_vinculo_ativo():
    credenciais = sem_comentarios(
        corpo_da_rotina_no_code("fn_get_login_credentials")
    )
    empresas = sem_comentarios(corpo_da_rotina_no_code("fn_my_companies"))

    assert re.search(r"cd\.active\s+AND\s+c\.active", credenciais, re.I)
    assert re.search(r"cd\.active\s+AND\s+c\.active", empresas, re.I)


# ---------------------------------------------------------------------- H14


AUTORIA = ("products", "categories", "clients", "suppliers")


@pytest.mark.parametrize("tabela", AUTORIA + ("stock_movements", "sales"))
def test_tabela_de_escrita_tem_coluna_de_autoria(tabela):
    """O critério "registrar o usuário autenticado" exige onde registrar."""
    assert "created_by" in colunas_da_tabela(tabela, sql_do_code()), (
        f"{tabela} não tem created_by"
    )


@pytest.mark.parametrize(
    "rotina,tabela",
    [
        ("fn_create_products", "products"),
        ("fn_create_categories", "categories"),
        ("fn_create_client", "clients"),
        ("fn_create_supplier", "suppliers"),
    ],
)
def test_criacao_grava_o_usuario_autenticado(rotina, tabela):
    """A coluna existir não basta: a função precisa preenchê-la.

    `fn_current_user_id()` é a única fonte aceitável aqui. Receber o autor por
    parâmetro deixaria o chamador escolher em nome de quem agiu.
    """
    corpo = sem_comentarios(corpo_da_rotina_no_code(rotina))
    # Ancorado em RETURNING, e não no primeiro `)`: a lista de VALUES tem
    # parênteses aninhados (`btrim(p_name)`), que fechariam a captura cedo.
    insercao = re.search(
        rf"INSERT INTO public\.{tabela}\s*\((.*?)\)\s*VALUES\s*\((.*)\)\s*RETURNING",
        corpo,
        re.S | re.I,
    )

    assert insercao, f"{rotina} não insere em {tabela}"
    assert "created_by" in insercao.group(1)
    assert "fn_current_user_id()" in insercao.group(2)


def test_auditoria_de_perfil_e_escrita_por_trigger():
    """A auditoria mora num trigger, e não dentro de cada função.

    Cinco caminhos escrevem em company_users. Se o registro morasse em cada
    um, o sexto nasceria sem auditoria — foi esse o raciocínio que já tinha
    posto `keep_admin` num trigger.
    """
    code = sem_comentarios(sql_do_code())

    assert re.search(
        r"CREATE TRIGGER trg_company_users_log_role\s+AFTER INSERT OR UPDATE\s+"
        r"ON public\.company_users",
        code,
        re.I,
    )
    corpo = sem_comentarios(corpo_da_rotina_no_code("trg_company_users_log_role"))
    assert "INSERT INTO public.role_change_log" in corpo
    assert "fn_current_user_id()" in corpo


def test_auditoria_guarda_papel_anterior_e_novo():
    """Sem o papel anterior, o log não responde "o que mudou"."""
    colunas = colunas_da_tabela("role_change_log", sql_do_code())

    assert {"actor_id", "target_user_id", "role_before", "role_after",
            "active_before", "active_after", "changed_on"} <= set(colunas)


def test_aplicacao_nao_escreve_na_auditoria():
    """Só SELECT é concedido: log reescrevível não é evidência de nada."""
    seguranca = sem_comentarios(SEGURANCA_SQL.read_text(encoding="utf-8"))

    assert re.search(r"GRANT SELECT ON[^;]*role_change_log", seguranca, re.S | re.I)
    assert not re.search(
        r"GRANT\s+(?:ALL|INSERT|UPDATE|DELETE)[^;]*role_change_log", seguranca, re.S | re.I
    )


def test_auditoria_so_e_lida_pelo_admin_da_empresa():
    """O log diz quem recebeu qual acesso: mesma alçada de listar usuários."""
    seguranca = sem_comentarios(SEGURANCA_SQL.read_text(encoding="utf-8"))
    policy = re.search(
        r"CREATE POLICY role_change_log_select.*?;", seguranca, re.S | re.I
    )

    assert policy, "policy de leitura do role_change_log não encontrada"
    assert re.search(r"fn_has_role\s*\(\s*company_id\s*,\s*ARRAY\s*\[\s*'ADMIN'\s*\]",
                     policy.group(0), re.I)
    assert re.search(r"ALTER TABLE public\.role_change_log\s+ENABLE ROW LEVEL SECURITY",
                     seguranca, re.I)


# ---------------------------------------------------------------------- H11
# O ajuste manual precisa aplicar sobre um banco que JÁ TEM movimentações, e
# sobre um remoto que já divergiu do repositório uma vez. Por isso tudo aqui
# é idempotente: `IF NOT EXISTS`, `DO` com guarda, e nenhuma recriação de
# tabela.

H11 = "h11_manual_stock_adjustment"


def arquivo_h11():
    achados = [f for f in arquivos() if H11 in f.name]
    assert achados, f"migration {H11} não encontrada"
    return achados[0]


def test_h11_vem_depois_de_todas_as_anteriores():
    assert arquivo_h11() == arquivos()[-1], (
        "a migration da H11 precisa ser a última da cadeia; "
        "timestamp menor aplica antes de dependência que já existe"
    )


def test_h11_abre_a_propria_transacao():
    """`supabase db push` manda cada comando em autocommit.

    Sem o BEGIN do próprio arquivo, uma falha no meio deixa metade aplicada
    — foi a lição que b92c490 registrou.
    """
    texto = arquivo_h11().read_text(encoding="utf-8")

    assert re.search(r"^\s*BEGIN;", texto, re.M)
    assert re.search(r"^\s*COMMIT;", texto, re.M)


def test_h11_cria_o_tipo_sem_quebrar_se_ele_ja_existir():
    texto = arquivo_h11().read_text(encoding="utf-8")

    assert "to_regtype('public.adjustment_reason')" in texto, (
        "criar o tipo sem guarda falha no banco que já o tem"
    )


def test_h11_adiciona_colunas_sem_recriar_a_tabela():
    texto = arquivo_h11().read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS adjustment_reason" in texto
    assert "ADD COLUMN IF NOT EXISTS counted_balance" in texto
    assert "DROP TABLE" not in texto.upper(), "migration destrutiva: perde histórico"


def test_h11_declara_as_duas_constraints():
    texto = arquivo_h11().read_text(encoding="utf-8")

    assert "ck_movements_adjustment_pair" in texto
    assert "ck_movements_adjustment_detail" in texto


def test_h11_cria_a_funcao_e_concede_execute():
    texto = arquivo_h11().read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION public.fn_register_adjustment" in texto
    assert re.search(
        r"GRANT EXECUTE ON FUNCTION public\.fn_register_adjustment", texto
    ), "sem GRANT a função aplica e o app quebra em runtime"
