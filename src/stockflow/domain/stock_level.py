"""Situação de estoque de um produto (US03 / US04).

ESTA É UMA TRADUÇÃO LITERAL de `public.fn_stock_state`
(`database/code/procedures/04_stock.sql`), que por sua vez alimenta a view
`vw_stock_situation`. O banco é a fonte da regra; este módulo é o espelho.

Por que o espelho, e não só a view: a tela precisa recalcular o status quando
o usuário muda o estoque no formulário, antes de qualquer ida ao banco, e o
modo de demonstração não tem banco nenhum. Mas espelho que diverge é pior do
que espelho nenhum — a tela mostraria "Crítico" onde um relatório SQL mostra
"Baixo", e as duas respostas seriam defensáveis.

AUSENTE E ZERO SÃO COISAS DIFERENTES, e a distinção é o ponto da US03:

- mínimo AUSENTE (`None`) -> nunca alerta. Não há limiar configurado, então
  não há o que comparar, e inventar um faria o produto alertar por uma regra
  que ninguém escolheu.
- mínimo ZERO -> alerta quando o saldo chega a zero. É uma configuração
  legítima e deliberada: "me avise quando acabar".

A versão anterior tratava os dois como o mesmo valor (`NOT_CONFIGURED = 0`),
e com isso quem configurava zero nunca era avisado. Daí `to_min` existir ao
lado de `to_int`: para o mínimo, `None` é um valor de domínio, não um erro a
tolerar.

Qualquer mudança aqui precisa de mudança equivalente em `fn_stock_state`, e
vice-versa.
"""

# Valor que o formulário sugere quando alguém opta por configurar um mínimo.
# NÃO é o padrão de um cadastro novo: o mínimo é opcional, então produto novo
# nasce SEM mínimo e só ganha um quando o usuário escolhe.
DEFAULT_MINIMUM_STOCK = 10

# Ausência de mínimo. `None`, e não zero: zero é uma configuração válida que
# alerta ao zerar o saldo, e colapsar os dois era o que impedia a US03.
NOT_CONFIGURED = None

NORMAL = "Normal"
ATTENTION = "Atenção"
LOW = "Baixo"
CRITICAL = "Crítico"

# Não é situação de estoque: é situação de cadastro (US02). Fica aqui porque
# a tabela mostra os dois na mesma coluna, e quem lê a coluna precisa de um
# lugar só para os rótulos possíveis.
INACTIVE = "Inativo"

# `public.stock_state` -> rótulo da tela. O enum do banco é em caixa alta e
# sem acento; traduzir aqui mantém o valor gravado intacto, como em
# `presentation/roles.py`.
LABEL_BY_STATE = {
    "NORMAL": NORMAL,
    "ATENCAO": ATTENTION,
    "BAIXO": LOW,
    "CRITICO": CRITICAL,
}

# Situações em que o produto está em ou abaixo do mínimo configurado — a
# seleção que a US04 pede. Derivada da regra, não escrita à mão: é o conjunto
# dos estados que `fn_stock_state` produz quando `p_stock <= p_min`.
BELOW_MINIMUM = (CRITICAL, LOW)

# Da pior para a melhor. Serve para ordenar por criticidade sem espalhar a
# noção de "pior" por quem desenha a tela.
SEVERITY = {CRITICAL: 0, LOW: 1, ATTENTION: 2, NORMAL: 3}


def to_int(valor, default: int = 0) -> int:
    """Converte estoque/mínimo para inteiro, sem nunca levantar.

    O catálogo guarda estoque como texto ("18") e o mínimo como inteiro, mas
    os dois passam por formulário, importação e banco. Qualquer um pode
    chegar vazio, `None` ou com lixo; derrubar a montagem da tabela por causa
    de uma célula é pior do que tratar o valor como ausente.
    """
    try:
        return int(str(valor).strip() or default)
    except (ValueError, TypeError):
        return default


def to_min(valor):
    """Mínimo do produto, PRESERVANDO a ausência.

    Diferente de `to_int`, que é desenhado para nunca devolver `None` e por
    isso não serve aqui: converter ausência em zero é exatamente o bug que a
    US03 fecha.

    `"—"` entra na lista de ausentes porque é o que a tabela de Estoque
    escreve na própria célula quando não há mínimo, e ela relê as linhas a
    cada busca e a cada clique de filtro. Sem este caso, a segunda leitura
    trataria o travessão como lixo e o produto mudaria de situação no meio de
    uma digitação.
    """
    if valor is None:
        return NOT_CONFIGURED
    texto = str(valor).strip()
    if texto in ("", "—", "None"):
        return NOT_CONFIGURED
    try:
        return int(texto)
    except (ValueError, TypeError):
        return NOT_CONFIGURED


def derive_stock_status(stock, minimum=NOT_CONFIGURED) -> str:
    """Situação do produto, igual a `fn_stock_state(p_stock, p_min)`.

    A ordem das faixas é a mesma do SQL, e ela importa:

    1. mínimo ausente -> `Normal`. Sem limiar não há o que comparar. É isto
       que implementa o "excluir produtos sem mínimo definido" da US04.
    2. saldo zerado ou negativo -> `Crítico`. Vem ANTES do teste de mínimo
       zero porque "sem unidade em mãos" não depende de qual era o mínimo —
       e é justamente aqui que o mínimo zero passa a alertar.
    3. mínimo zero e saldo positivo -> `Normal`. Cláusula própria, não um
       resto: sem ela o saldo cairia em `saldo < 0 * 1,2`, que é falso para
       tudo, e o resultado certo sairia por acidente.
    4. saldo <= mínimo -> `Baixo`. O `<=` é o que faz o saldo IGUAL ao mínimo
       entrar no alerta, como o critério da US04 exige.
    5. saldo < mínimo × 1,2 -> `Atenção`. Faixa de aproximação.
    6. o resto -> `Normal`.
    """
    minimo = to_min(minimum)
    if minimo is None:
        return NORMAL

    quantidade = to_int(stock)
    if quantidade <= 0:
        return CRITICAL
    if minimo == 0:
        return NORMAL
    if quantidade <= minimo:
        return LOW
    if quantidade < minimo * 1.2:
        return ATTENTION
    return NORMAL


def state_to_label(state) -> str:
    """Valor de `public.stock_state` para o rótulo da tela."""
    texto = str(state or "").strip().upper()
    return LABEL_BY_STATE.get(texto, NORMAL)


def is_below_minimum(status) -> bool:
    """Diz se a situação significa "em ou abaixo do mínimo" (US04)."""
    return status in BELOW_MINIMUM
