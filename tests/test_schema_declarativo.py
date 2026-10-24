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

import pytest

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


# ---------------------------------------------------------------------- H11
# O ajuste manual não é uma terceira espécie de movimentação: é uma ENTRADA
# ou SAIDA comum marcada por `adjustment_reason`. Estes testes cobram que a
# marca e as suas regras estejam na FONTE declarativa, não só na migration —
# `code/` é o que o `declarative sync` diffa contra o banco, e o que ficar de
# fora dele o diff seguinte propõe derrubar.

CODE_SQL = "\n".join(
    re.sub(r"--[^\n]*", "", p.read_text(encoding="utf-8"))
    for p in sorted(CODE.rglob("*.sql"))
)


def test_h11_tipo_do_motivo_existe_com_os_seis_valores():
    achado = re.search(
        r"CREATE TYPE\s+public\.adjustment_reason\s+AS ENUM\s*\((.*?)\)",
        CODE_SQL,
        re.S | re.I,
    )
    assert achado, "tipo public.adjustment_reason não declarado em database/code"

    valores = set(re.findall(r"'(\w+)'", achado.group(1)))
    assert valores == {
        "CONTAGEM", "QUEBRA", "PERDA", "VENCIMENTO", "DEVOLUCAO", "OUTRO",
    }


def test_h11_colunas_do_ajuste_estao_em_stock_movements():
    corpo = re.search(
        r"CREATE TABLE\s+public\.stock_movements\s*\((.*?)\n\);", CODE_SQL, re.S | re.I
    )
    assert corpo, "tabela stock_movements não encontrada em database/code"

    texto = corpo.group(1)
    assert "adjustment_reason public.adjustment_reason" in texto
    assert "counted_balance" in texto


def test_h11_as_constraints_do_ajuste_sao_nomeadas():
    """Nome explícito nas três, para que a migration possa guardá-las.

    CHECK anônimo ganha nome gerado pelo Postgres, que a migration não teria
    como consultar em `pg_constraint` — e os dois lados passariam a declarar
    a mesma regra com identidades diferentes.
    """
    for nome in ("ck_movements_counted_balance",
                 "ck_movements_adjustment_pair",
                 "ck_movements_adjustment_detail"):
        assert f"CONSTRAINT {nome}" in CODE_SQL, f"constraint {nome} sem nome em database/code"


def _corpo_de_stock_movements(sql: str) -> str:
    corpo = re.search(
        r"CREATE TABLE\s+public\.stock_movements\s*\((.*?)\n\);", sql, re.S | re.I
    )
    assert corpo, "tabela stock_movements não encontrada em database/code"
    return corpo.group(1)


def _predicado_do_constraint(corpo_tabela: str, nome: str) -> str:
    """Texto do CHECK de uma constraint nomeada, com parênteses balanceados.

    Os predicados de H11 aninham parênteses (os dois lados do par, o
    `IS DISTINCT FROM`); um corte não guloso até o primeiro `)` cortaria o
    predicado pela metade. Contar profundidade é o que permite extrair o
    predicado inteiro e avaliar a LÓGICA dele, em vez de só confirmar que o
    nome da constraint aparece em algum lugar do arquivo.
    """
    abertura = re.search(rf"CONSTRAINT\s+{nome}\s+CHECK\s*\(", corpo_tabela)
    assert abertura, f"constraint {nome} não encontrada no corpo de stock_movements"
    i = abertura.end()
    profundidade = 1
    while profundidade > 0:
        if corpo_tabela[i] == "(":
            profundidade += 1
        elif corpo_tabela[i] == ")":
            profundidade -= 1
        i += 1
    return corpo_tabela[abertura.end() : i - 1]


def _avaliar_booleano_sql(expressao: str) -> bool:
    """Avalia um predicado SQL já reduzido a `True`/`False`/`AND`/`OR`/parênteses.

    Não é um parser de SQL: é o suficiente para distinguir um `AND` de um
    `OR` depois que as comparações de nulidade/igualdade já viraram
    booleanos Python. A checagem de resíduo garante que nenhum token do
    predicado real escapou da substituição — um CHECK apontado para a
    coluna errada, por exemplo, deixaria um identificador aqui.
    """
    expressao = re.sub(r"\bAND\b", "and", expressao)
    expressao = re.sub(r"\bOR\b", "or", expressao)
    residual = re.sub(r"True|False|and|or|\(|\)|\s", "", expressao)
    assert residual == "", f"token não reconhecido no predicado: {residual!r}"
    # Envolto em parênteses: o predicado original quebra linha com indentação
    # (ele vem de dentro de um CHECK multilinha), e isso quebraria `eval` de
    # uma expressão "nua" com `IndentationError`. Um parêntese por fora
    # resolve sem mudar o valor lógico.
    return eval("(" + expressao + ")")  # noqa: S307 — só True/False/and/or/parênteses sobrevivem ao residual acima


def test_h11_o_par_motivo_contagem_e_tudo_ou_nada():
    """Motivo sem contagem (ou o contrário) seria ajuste pela metade.

    Avalia a LÓGICA do predicado para os quatro casos de nulidade, não só a
    presença do nome da constraint: um `AND` virado `OR` numa das metades
    deixaria o nome intacto e aceitaria a dupla pela metade — exatamente o
    que este CHECK existe para recusar, e o que um `"ck_movements_..." in
    CODE_SQL` nunca enxergaria.
    """
    corpo = _corpo_de_stock_movements(CODE_SQL)
    predicado = _predicado_do_constraint(corpo, "ck_movements_adjustment_pair")

    casos = {
        (True, True): True,  # os dois ausentes: movimentação comum, sem ajuste
        (True, False): False,  # motivo ausente, contagem presente: pela metade
        (False, True): False,  # motivo presente, contagem ausente: pela metade
        (False, False): True,  # os dois presentes: ajuste completo
    }
    for (reason_is_null, counted_is_null), esperado in casos.items():
        expressao = predicado
        expressao = re.sub(
            r"adjustment_reason\s+IS\s+NOT\s+NULL", str(not reason_is_null), expressao
        )
        expressao = re.sub(r"adjustment_reason\s+IS\s+NULL", str(reason_is_null), expressao)
        expressao = re.sub(
            r"counted_balance\s+IS\s+NOT\s+NULL", str(not counted_is_null), expressao
        )
        expressao = re.sub(r"counted_balance\s+IS\s+NULL", str(counted_is_null), expressao)

        obtido = _avaliar_booleano_sql(expressao)
        assert obtido is esperado, (
            f"ck_movements_adjustment_pair com adjustment_reason "
            f"{'NULL' if reason_is_null else 'NOT NULL'} e counted_balance "
            f"{'NULL' if counted_is_null else 'NOT NULL'}: esperado {esperado}, obtido {obtido}"
        )


def test_h11_outro_sem_detalhe_e_recusado_pelo_banco():
    """A justificativa é regra do banco, não cortesia da tela.

    Avalia a LÓGICA do predicado para motivo e nota concretos, não só a
    presença do nome da constraint: um CHECK apontado para a coluna errada,
    ou sempre verdadeiro, deixaria o nome intacto e aceitaria `OUTRO` sem
    dizer nada — e o critério de aceite fala em justificativa, não em campo
    de formulário.
    """
    corpo = _corpo_de_stock_movements(CODE_SQL)
    predicado = _predicado_do_constraint(corpo, "ck_movements_adjustment_detail")

    def avaliar(motivo: str, nota: str) -> bool:
        expressao = predicado.replace(
            "adjustment_reason IS DISTINCT FROM 'OUTRO'", str(motivo != "OUTRO")
        )
        nota_efetiva = (nota or "").strip()
        expressao = re.sub(
            r"btrim\(coalesce\(note,\s*''\)\)\s*<>\s*''",
            str(nota_efetiva != ""),
            expressao,
        )
        return _avaliar_booleano_sql(expressao)

    assert avaliar("OUTRO", "") is False, "OUTRO sem justificativa deveria violar o CHECK"
    assert avaliar("OUTRO", "   ") is False, (
        "OUTRO com nota só de espaços em branco deveria violar o CHECK"
    )
    assert avaliar("OUTRO", "quebrou na entrega") is True, (
        "OUTRO com justificativa real deveria passar no CHECK"
    )
    assert avaliar("CONTAGEM", "") is True, (
        "motivo diferente de OUTRO não exige justificativa"
    )


def test_h11_a_funcao_de_ajuste_existe_e_e_security_definer():
    corpo = re.search(
        r"CREATE OR REPLACE FUNCTION\s+public\.fn_register_adjustment\b(.*?)\$\$;",
        CODE_SQL,
        re.S | re.I,
    )
    assert corpo, "fn_register_adjustment não declarada em database/code"
    assert "SECURITY DEFINER" in corpo.group(1)
    assert "FOR UPDATE" in corpo.group(1), (
        "sem FOR UPDATE dois ajustes simultâneos calculam a diferença sobre "
        "o mesmo saldo e um sobrescreve o outro"
    )


def test_h11_a_funcao_de_ajuste_confere_o_saldo_resultante_depois_de_gravar():
    """O terceiro critério da H11 é esta releitura, não a aritmética.

    O trigger `trg_stock_movements_apply` produz o saldo certo sozinho, então
    um teste que só confira "o saldo final é o contado" mede o TRIGGER e
    passa igualzinho com a releitura apagada. O que a releitura compra é a
    outra metade: se o saldo gravado discordar do contado, a transação
    inteira volta atrás. Daí a asserção ser sobre o texto da função — é o
    único lugar onde a garantia existe sem um Postgres por perto.

    A busca começa DEPOIS do `INSERT` de propósito: reler o saldo antes de
    gravar não garante nada, porque o trigger ainda não rodou.
    """
    corpo = re.search(
        r"CREATE OR REPLACE FUNCTION\s+public\.fn_register_adjustment\b(.*?)\$\$;",
        CODE_SQL,
        re.S | re.I,
    )
    assert corpo, "fn_register_adjustment não declarada em database/code"

    partes = corpo.group(1).split("INSERT INTO public.stock_movements", 1)
    assert len(partes) == 2, "fn_register_adjustment não grava a movimentação"

    assert re.search(
        r"SELECT\s+stock\s+INTO\s+v_final\b.*?"
        r"IF\s+v_final\s*<>\s*p_counted_balance\s+THEN.*?"
        r"RAISE\s+EXCEPTION",
        partes[1],
        re.S | re.I,
    ), (
        "sem reler products.stock depois do INSERT e levantar quando ele "
        "difere do contado, o critério 3 vira expectativa: um saldo "
        "divergente seria gravado em vez de desfazer a transação"
    )


def test_h11_a_funcao_de_ajuste_esta_na_allowlist_de_execute():
    """Função fora da allowlist aplica no banco e quebra o app em runtime."""
    allowlist = (CODE / "policies" / "01_security.sql").read_text(encoding="utf-8")
    assert "'fn_register_adjustment'" in allowlist


# ---------------------------------------------------------------------- H09
# "Alteração controlada de preço e custo": controlada quer dizer que a mudança
# deixa rastro. O rastro já existia e parava na metade — `trg_log_price_edit`
# só olhava `sell_price`, então mexer no custo era a única escrita de catálogo
# que ninguém conseguia reconstruir depois.
#
# Os dois campos vão para o MESMO log, com uma coluna dizendo qual mudou, e
# não para duas tabelas: "o que aconteceu com o preço deste produto" tem que
# continuar sendo uma consulta só, ordenada por tempo.


def _corpo_do_price_edit_log(sql: str) -> str:
    # `IF NOT EXISTS` é obrigatório aqui: a tabela nasceu no remoto antes de
    # existir no repositório, e a forma curta não casaria com a declaração.
    corpo = re.search(
        r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?public\.price_edit_log\s*\((.*?)\n\);",
        sql,
        re.S | re.I,
    )
    assert corpo, "tabela price_edit_log não encontrada em database/code"
    return corpo.group(1)


def _corpo_do_trigger_de_preco(sql: str) -> str:
    corpo = re.search(
        r"CREATE OR REPLACE FUNCTION\s+public\.trg_log_price_edit\b(.*?)\$\$;",
        sql,
        re.S | re.I,
    )
    assert corpo, "trg_log_price_edit não declarada em database/code"
    return corpo.group(1)


def test_h09_tipo_do_campo_auditado_tem_preco_e_custo():
    """Lista fechada, como `adjustment_reason`.

    Campo auditado em `text` aceitaria 'sell_price', 'SELLPRICE' e 'venda' na
    mesma coluna, e a consulta por histórico de preço passaria a depender de
    quem escreveu a linha.
    """
    achado = re.search(
        r"CREATE TYPE\s+public\.price_edit_field\s+AS ENUM\s*\((.*?)\)",
        CODE_SQL,
        re.S | re.I,
    )
    assert achado, "tipo public.price_edit_field não declarado em database/code"

    assert set(re.findall(r"'(\w+)'", achado.group(1))) == {"SELL_PRICE", "BUY_PRICE"}


def test_h09_log_de_preco_guarda_qual_campo_mudou():
    texto = _corpo_do_price_edit_log(CODE_SQL)

    assert "field public.price_edit_field" in texto, (
        "sem a coluna, a linha de custo fica indistinguível da de preço e o "
        "histórico de venda passa a somar as duas"
    )


def test_h09_trigger_dispara_na_mudanca_de_custo_tambem():
    assert re.search(
        r"AFTER UPDATE OF\s+sell_price\s*,\s*buy_price\s+ON public\.products",
        CODE_SQL,
        re.I,
    ), "trigger só em sell_price nunca acorda numa edição de custo"


def test_h09_trigger_registra_os_dois_campos_pelo_valor_anterior():
    """Cada campo compara o SEU anterior com o SEU novo.

    Um `IF` só, cobrindo os dois, gravaria a mudança de custo com os valores
    de preço — o log diria que algo mudou e mentiria sobre o quê.
    """
    corpo = _corpo_do_trigger_de_preco(CODE_SQL)

    assert re.search(
        r"OLD\.sell_price IS DISTINCT FROM NEW\.sell_price", corpo, re.I
    ), "o campo de venda perdeu a própria comparação"
    assert re.search(
        r"OLD\.buy_price IS DISTINCT FROM NEW\.buy_price", corpo, re.I
    ), "sem comparar buy_price, a edição de custo não gera linha"
    assert "'SELL_PRICE'" in corpo and "'BUY_PRICE'" in corpo, (
        "o trigger precisa carimbar qual campo originou cada linha"
    )


def test_h09_o_log_aceita_custo_que_nao_existia_antes():
    """`products.buy_price` é nullable; `old_price NOT NULL` não sobrevive a isso.

    Informar o custo pela primeira vez tem `OLD.buy_price IS NULL`. Com o par
    antes/depois obrigatório, o INSERT da auditoria violaria NOT NULL e
    derrubaria o UPDATE do produto — a auditoria passaria a IMPEDIR a edição
    que ela existe para registrar.

    As saídas que mantinham NOT NULL eram piores: gravar `0` inventa um custo
    que nunca foi praticado, e pular a linha deixa justamente a primeira
    definição de custo sem rastro. `NULL` é a resposta certa para "antes não
    havia valor", e o CHECK garante que pelo menos um dos lados exista.
    """
    texto = _corpo_do_price_edit_log(CODE_SQL)

    assert not re.search(r"old_price\s+numeric\s+NOT NULL", texto, re.I), (
        "old_price NOT NULL recusa a primeira definição de custo"
    )
    assert not re.search(r"new_price\s+numeric\s+NOT NULL", texto, re.I), (
        "new_price NOT NULL recusa a limpeza de custo"
    )
    assert "CONSTRAINT ck_price_edit_log_value_present" in texto, (
        "sem o CHECK, uma linha com os dois lados nulos não diz nada"
    )


# ------------------------------------------- H09 · consulta do histórico
# Gravar o rastro e não conseguir lê-lo não entrega a história. A consulta
# mora numa função, e não num SELECT da tela, pela mesma razão de
# `fn_list_company_users`: a auditoria só faz sentido com o código do produto
# e o nome de quem mudou, que vivem em outras tabelas.


def _corpo_da_consulta_de_historico(sql: str) -> str:
    corpo = re.search(
        r"CREATE OR REPLACE FUNCTION\s+public\.fn_list_price_edits\b(.*?)\$\$;",
        sql,
        re.S | re.I,
    )
    assert corpo, "fn_list_price_edits não declarada em database/code"
    return corpo.group(1)


def test_h09_consulta_do_historico_e_security_definer_com_search_path():
    corpo = _corpo_da_consulta_de_historico(CODE_SQL)

    assert "SECURITY DEFINER" in corpo
    assert re.search(r"SET search_path = public", corpo, re.I), (
        "função SECURITY DEFINER sem search_path fixo aceita sequestro de schema"
    )


def test_h09_consulta_do_historico_exige_admin():
    """Mesma alçada da policy que já protege a tabela.

    `price_edit_log_select` restringe a leitura ao ADMIN da empresa. Uma
    função SECURITY DEFINER passa por cima da RLS, então ou ela repete a
    checagem ou vira a porta dos fundos da própria auditoria.
    """
    corpo = _corpo_da_consulta_de_historico(CODE_SQL)

    assert re.search(r"fn_is_admin\s*\(", corpo, re.I), (
        "sem a guarda de ADMIN, SECURITY DEFINER entrega o log a qualquer papel"
    )
    assert "insufficient_privilege" in corpo


def test_h09_consulta_ordena_do_mais_recente_e_desempata_pelo_id():
    """O desempate não é preciosismo: `now()` é constante na transação.

    Preço e custo alterados no mesmo UPDATE recebem `last_updated_on`
    IDÊNTICO. Ordenando só por tempo, a ordem relativa dessas duas linhas
    fica indefinida e a tela as embaralha entre uma consulta e outra —
    "cronológica" viraria "quase cronológica".
    """
    corpo = _corpo_da_consulta_de_historico(CODE_SQL)

    assert re.search(
        r"ORDER BY\s+\w*\.?last_updated_on DESC\s*,\s*\w*\.?id DESC", corpo, re.I
    ), "ordem cronológica decrescente com desempate estável pelo id"


def test_h09_consulta_filtra_por_produto_sem_exigir_o_filtro():
    """Um parâmetro, dois usos: a lista inteira e a de um produto."""
    assinatura = re.search(
        r"CREATE OR REPLACE FUNCTION\s+public\.fn_list_price_edits\s*\((.*?)\)\s*RETURNS",
        CODE_SQL,
        re.S | re.I,
    )
    assert assinatura, "assinatura de fn_list_price_edits não encontrada"

    assert re.search(r"p_product_id\s+uuid\s+DEFAULT NULL", assinatura.group(1), re.I)
    corpo = _corpo_da_consulta_de_historico(CODE_SQL)
    assert re.search(r"p_product_id IS NULL OR", corpo, re.I), (
        "o filtro opcional precisa ser nulo-tolerante dentro do WHERE"
    )


def test_h09_consulta_do_historico_esta_na_allowlist_de_execute():
    allowlist = (CODE / "policies" / "01_security.sql").read_text(encoding="utf-8")
    assert "'fn_list_price_edits'" in allowlist, (
        "função fora da allowlist aplica no banco e quebra o app em runtime"
    )


# --------------------------------------------------------------------- US17
# A reversão de venda é uma RELAÇÃO, não um atributo do cabeçalho. Estes
# testes cobram que a tabela de vínculo e os dois enums estejam na FONTE
# declarativa: `code/` é o que o declarative sync diffa contra o banco, e o
# que ficar de fora dele o diff seguinte propõe derrubar.


def corpo_da_tabela(nome: str) -> str:
    """Texto entre os parênteses de um CREATE TABLE em database/code."""
    achado = re.search(
        rf"CREATE TABLE\s+{SE_NAO_EXISTIR}public\.{nome}\s*\((.*?)\n\);",
        CODE_SQL,
        re.S,
    )
    return achado.group(1) if achado else ""


def test_us17_status_de_venda_inclui_devolvida():
    """A fonte declarativa descreve o ESTADO FINAL do tipo.

    `code/` é aplicado em banco limpo (`verify_postgres.py --schema`), onde
    o tipo nasce com os quatro rótulos. Quem precisa de `ALTER TYPE` é a
    migration, que roda sobre um remoto que já tem o tipo com três.
    """
    achado = re.search(
        r"CREATE TYPE public\.sale_status AS ENUM\s*\((.*?)\)", CODE_SQL, re.S
    )
    assert achado, "tipo public.sale_status não declarado em database/code"
    assert set(re.findall(r"'(\w+)'", achado.group(1))) == {
        "PENDENTE",
        "CONCLUIDA",
        "CANCELADA",
        "DEVOLVIDA",
    }


def test_us17_migration_acrescenta_devolvida_ao_tipo_existente():
    """`CREATE TYPE` no remoto falharia: o tipo já existe com três rótulos."""
    migration = (
        MIGRATIONS / "20261024120000_us17_sales_history.sql"
    ).read_text(encoding="utf-8")
    assert (
        "ALTER TYPE public.sale_status ADD VALUE IF NOT EXISTS 'DEVOLVIDA'"
        in migration
    )


def test_us17_especie_de_reversao_tem_os_dois_valores():
    achado = re.search(
        r"CREATE TYPE public\.sale_reversal_kind AS ENUM\s*\((.*?)\)",
        CODE_SQL,
        re.S,
    )
    assert achado, "tipo public.sale_reversal_kind não declarado em database/code"
    assert set(re.findall(r"'(\w+)'", achado.group(1))) == {
        "CANCELAMENTO",
        "DEVOLUCAO",
    }


def test_us17_reversao_e_terminal_por_indice_unico():
    """Venda revertida não vira outra coisa depois.

    A função confere também, mas o UNIQUE é o que torna a regra verdadeira
    para quem chegue por outro caminho.
    """
    corpo = corpo_da_tabela("sale_reversals")
    assert corpo, "tabela sale_reversals não encontrada em database/code"
    assert "UNIQUE (sale_id)" in corpo


def test_us17_reversao_escopa_por_coluna_propria():
    corpo = corpo_da_tabela("sale_reversals")
    assert "company_id  uuid NOT NULL" in corpo
    assert "REFERENCES public.sales (company_id, id) ON DELETE CASCADE" in corpo


def test_us17_reversao_exige_motivo_nao_vazio():
    corpo = corpo_da_tabela("sale_reversals")
    assert "CHECK (btrim(reason) <> '')" in corpo


def test_us17_aplicacao_nao_escreve_na_tabela_de_reversao():
    """Mesma proteção de `sales`: só SELECT. A escrita é das funções."""
    politicas = (CODE / "policies" / "01_security.sql").read_text(encoding="utf-8")
    concedido = politicas.split("GRANT SELECT ON", 1)[1].split(";", 1)[0]
    assert "public.sale_reversals" in concedido
    assert "CREATE POLICY sale_reversals_select ON public.sale_reversals" in politicas
    # Tolerante ao alinhamento: este arquivo alinha a coluna do ENABLE.
    assert re.search(
        r"ALTER TABLE public\.sale_reversals\s+ENABLE ROW LEVEL SECURITY", politicas
    )


def corpo_da_funcao(nome: str) -> str:
    """Texto de uma função em database/code, do seu CREATE até o próximo."""
    achado = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{nome}\b(.*?)"
        r"(?=CREATE OR REPLACE FUNCTION|\Z)",
        CODE_SQL,
        re.S,
    )
    return achado.group(1) if achado else ""


def test_us17_consulta_repete_a_checagem_da_policy():
    """SECURITY DEFINER passa por cima da RLS.

    Sem `fn_is_member` na entrada, esta função vira a porta dos fundos do
    histórico — a mesma lição já registrada em fn_list_price_edits.
    """
    corpo = corpo_da_funcao("fn_list_sales")
    assert corpo, "fn_list_sales não declarada em database/code"
    assert "SECURITY DEFINER" in corpo
    assert "SET search_path = public" in corpo
    assert "fn_is_member(p_company_id)" in corpo


def test_us17_consulta_devolve_o_total_na_mesma_leitura():
    """Uma segunda contagem poderia divergir da página sob concorrência."""
    assert "count(*) OVER ()" in corpo_da_funcao("fn_list_sales")


def test_us17_consulta_desempata_a_ordem_pelo_id():
    """Sem desempate, a página seguinte repete ou pula linha."""
    assert re.search(r"ORDER BY.*?f\.id DESC", corpo_da_funcao("fn_list_sales"), re.S)


def test_us17_ordenacao_nunca_e_sql_dinamico():
    """Texto do chamador virando ORDER BY é injeção."""
    corpo = corpo_da_funcao("fn_list_sales")
    assert "EXECUTE " not in corpo
    for criterio in ("DATA_DESC", "DATA_ASC", "VALOR_DESC", "VALOR_ASC", "CLIENTE_ASC"):
        assert criterio in corpo, criterio


def test_us17_todos_os_filtros_sao_opcionais_e_combinaveis():
    corpo = corpo_da_funcao("fn_list_sales")
    for parametro, coluna in (
        ("p_from", "s.created_on >="),
        ("p_to", "s.created_on <"),
        ("p_client_id", "s.client_id ="),
        ("p_seller_id", "s.created_by ="),
        ("p_status", "s.status ="),
    ):
        # Tolerante ao alinhamento em coluna usado no WHERE da função.
        assert re.search(
            rf"{parametro}\s+IS NULL OR {re.escape(coluna)}", corpo
        ), parametro


def test_us17_consulta_limita_o_tamanho_da_pagina():
    """Página sem teto é `list_all` com outro nome."""
    corpo = corpo_da_funcao("fn_list_sales")
    assert "p_limit <= 0 OR p_limit > 200" in corpo


def test_us17_consulta_esta_na_allowlist_de_execute():
    allowlist = (CODE / "policies" / "01_security.sql").read_text(encoding="utf-8")
    assert "'fn_list_sales'" in allowlist, (
        "função fora da allowlist aplica no banco e quebra o app em runtime"
    )
