"""Situação de estoque de um produto (US03 / US04).

ESTA É UMA TRADUÇÃO LITERAL de `public.fn_stock_state`
(`database/code/procedures/04_stock.sql`), que por sua vez alimenta a view
`vw_stock_situation`. O banco é a fonte da regra; este módulo é o espelho.

Por que o espelho, e não só a view: a tela precisa recalcular o status quando
o usuário muda o estoque no formulário, antes de qualquer ida ao banco, e o
modo de demonstração não tem banco nenhum. Mas espelho que diverge é pior do
que espelho nenhum — a tela mostraria "Crítico" onde um relatório SQL mostra
"Baixo", e as duas respostas seriam defensáveis.

A versão anterior deste arquivo AFIRMAVA espelhar `fn_stock_state` e não
espelhava: divergia em 5 de 11 casos. As diferenças que importavam:

- produto SEM mínimo configurado era tratado como mínimo 10 e entrava no
  alerta; o banco devolve NORMAL. A US04 pede explicitamente "excluir
  produtos sem mínimo definido", então a versão antiga violava o critério;
- "Crítico" era `estoque × 2 <= mínimo`; no banco é só `estoque <= 0`;
- o estado `ATENCAO` (acima do mínimo, mas a menos de 20% dele) não existia.

Qualquer mudança aqui precisa de mudança equivalente em `fn_stock_state`, e
vice-versa.
"""

# Valor que o formulário SUGERE para um produto novo. Não é o padrão da
# regra: a regra trata mínimo ausente como "não configurado" e não alerta.
# São coisas diferentes, e misturá-las foi o que fez produto sem configuração
# aparecer no alerta.
DEFAULT_MINIMUM_STOCK = 10

# Mínimo "não configurado", espelhando `COALESCE(ps.min_quantity, 0)` da
# `vw_stock_situation`: zero e ausente significam a mesma coisa.
NOT_CONFIGURED = 0

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


def derive_stock_status(stock, minimum=None) -> str:
    """Situação do produto, igual a `fn_stock_state(p_stock, p_min)`.

    A ordem das faixas é a mesma do SQL, e ela importa:

    1. mínimo ausente ou zero -> `Normal`. Sem referência não há o que
       comparar, e inventar um mínimo faria o produto alertar por uma regra
       que ninguém configurou. É isto que implementa o "excluir produtos sem
       mínimo definido" da US04.
    2. saldo zerado ou negativo -> `Crítico`. Vem antes das comparações com
       o mínimo porque "sem unidade em mãos" não depende de quanto era o
       mínimo.
    3. saldo <= mínimo -> `Baixo`. O `<=` é o que faz o saldo IGUAL ao mínimo
       entrar no alerta, como o critério da US04 exige.
    4. saldo < mínimo × 1,2 -> `Atenção`. Faixa de aproximação: ainda acima
       do mínimo, perto o bastante para planejar reposição.
    5. o resto -> `Normal`.
    """
    minimo = to_int(minimum, NOT_CONFIGURED)
    if minimo <= NOT_CONFIGURED:
        return NORMAL

    quantidade = to_int(stock)
    if quantidade <= 0:
        return CRITICAL
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
