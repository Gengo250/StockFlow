"""Cada coluna que os adaptadores pedem precisa existir na fonte declarativa.

A tela de Vendas já respondeu `42703 column sales.client_name does not exist`
em produção. O erro não era de lógica: o adaptador pedia uma coluna que existia
no schema declarado e não no banco. Nenhum teste pegava isso, porque os testes
de adaptador usam cliente falso — ele devolve o que mandarem, inclusive colunas
inventadas.

Este teste fecha metade do buraco: cobra as consultas contra `database/code`,
que é a fonte declarativa. Renomear uma coluna no schema sem acertar a consulta
— ou o contrário — passa a falhar aqui.

A outra metade NÃO é coberta por teste nenhum e não dá para cobrir offline: se
o banco real divergir da fonte declarativa, só uma verificação contra o banco
acusa. Para isso existe `scripts/verify_postgres.py`.

A leitura é por `ast`, não por regex, porque `.select(...)` recebe literais
concatenados implicitamente:

    .select("id,client_name,total,created_on,"
            "sale_items(product_name,product_code,quantity)")

Regex pega só o primeiro pedaço e deixa o embed passar sem conferência — que é
justamente a parte mais fácil de errar.
"""

import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CODE = RAIZ / "database" / "code"
ADAPTADORES = RAIZ / "src" / "stockflow" / "infrastructure" / "repositories"


def tabelas_declaradas():
    """`{tabela: {coluna}}` a partir de database/code/tables/*.sql.

    Só as colunas indentadas com quatro espaços são nomes de coluna; esse é o
    estilo de toda a árvore. Linhas de CHECK, FOREIGN KEY e UNIQUE no fim da
    definição ficam de fora por não casarem com `^ {4}\\w+\\s`.
    """
    declaradas = {}
    for arquivo in sorted((CODE / "tables").glob("*.sql")):
        texto = arquivo.read_text(encoding="utf-8")
        for bloco in re.finditer(
            r"CREATE TABLE (?:IF NOT EXISTS )?public\.(\w+)\s*\((.*?)\n\);",
            texto,
            re.S,
        ):
            declaradas[bloco.group(1)] = set(
                re.findall(r"^ {4}(\w+)\s", bloco.group(2), re.M)
            )
    return declaradas


def views_declaradas():
    nomes = set()
    for arquivo in sorted((CODE / "views").glob("*.sql")):
        nomes.update(
            re.findall(
                r"CREATE (?:OR REPLACE )?VIEW\s+public\.(\w+)",
                arquivo.read_text(encoding="utf-8"),
                re.I,
            )
        )
    return nomes


def tabela_da_cadeia(no):
    """Acha o `.table("x")` que ancora este `.select(...)`.

    A cadeia é percorrida de fora para dentro porque o `.select` pode estar
    longe do `.table`: `table(t).select(c).eq(...).order(...)` é a forma comum
    nos adaptadores.
    """
    while isinstance(no, ast.Attribute) or isinstance(no, ast.Call):
        if isinstance(no, ast.Call):
            alvo = no.func
            if (isinstance(alvo, ast.Attribute) and alvo.attr == "table"
                    and no.args and isinstance(no.args[0], ast.Constant)
                    and isinstance(no.args[0].value, str)):
                return no.args[0].value
            no = alvo
        else:
            no = no.value
    return None


def fatia_no_topo(texto):
    """Quebra a lista de colunas ignorando vírgulas dentro de parênteses."""
    partes, atual, profundidade = [], "", 0
    for caractere in texto:
        if caractere == "(":
            profundidade += 1
        elif caractere == ")":
            profundidade -= 1
        if caractere == "," and profundidade == 0:
            partes.append(atual)
            atual = ""
        else:
            atual += caractere
    partes.append(atual)
    return [p.strip() for p in partes if p.strip()]


def pedidos_por_tabela(tabela, selecao):
    """`[(tabela, {coluna})]`, abrindo os embeds em entradas próprias.

    `sale_items(product_name,quantity)` dentro de um select em `sales` vira uma
    cobrança separada contra `sale_items`.
    """
    diretas, pedidos = set(), []
    for token in fatia_no_topo(selecao):
        embed = re.fullmatch(r"(\w+)\s*\((.*)\)", token, re.S)
        if embed:
            pedidos += pedidos_por_tabela(embed.group(1), embed.group(2))
        else:
            # `coluna:apelido` e `coluna->>chave` não são usados hoje; se
            # passarem a ser, o nome cru é o que precisa existir.
            diretas.add(re.split(r"[:\->]", token)[0].strip())
    if diretas:
        pedidos.append((tabela, diretas))
    return pedidos


def consultas():
    encontradas = []
    for arquivo in sorted(ADAPTADORES.glob("supabase_*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not (isinstance(no, ast.Call)
                    and isinstance(no.func, ast.Attribute)
                    and no.func.attr == "select"
                    and no.args
                    and isinstance(no.args[0], ast.Constant)
                    and isinstance(no.args[0].value, str)):
                continue
            tabela = tabela_da_cadeia(no.func.value)
            if tabela:
                encontradas += [
                    (arquivo.name, t, c)
                    for t, c in pedidos_por_tabela(tabela, no.args[0].value)
                ]
    return encontradas


def test_adapters_only_select_columns_the_schema_declares():
    declaradas = tabelas_declaradas()
    achadas = consultas()

    # Sem esta âncora o teste vira decoração: uma mudança de estilo que quebre
    # a leitura por `ast` passaria como "nenhuma consulta, nada a conferir".
    assert len(achadas) >= 10, f"a varredura encontrou poucas consultas: {achadas}"
    assert {t for _, t, _ in achadas} >= {"sales", "sale_items", "products"}

    erros = []
    for origem, tabela, colunas in achadas:
        if tabela not in declaradas:
            continue
        faltando = sorted(colunas - declaradas[tabela])
        if faltando:
            erros.append(f"{origem}: {tabela} não declara {faltando}")
    assert erros == [], "consultas pedem colunas inexistentes: " + "; ".join(erros)


def test_adapters_only_query_objects_the_schema_declares():
    """Nome de tabela errado não pode sumir no `continue` do teste acima."""
    conhecidos = set(tabelas_declaradas()) | views_declaradas()
    desconhecidos = sorted(
        {f"{origem}: {tabela}" for origem, tabela, _ in consultas()
         if tabela not in conhecidos}
    )
    assert desconhecidos == [], (
        "consultas usam objetos que não existem em database/code: "
        + "; ".join(desconhecidos)
    )
