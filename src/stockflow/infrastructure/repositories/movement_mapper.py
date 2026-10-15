"""Tradução entre a linha de `public.stock_movements` e a linha da tela.

A tabela de Movimentações consome tuplas neste contrato, DEZ posições SEMPRE
(ver a nota em `row_to_movement` sobre por que a cauda deixou de ser opcional):

    (id, código, nome do produto, espécie, quantidade, situação, nota, quando,
     fornecedor, motivo)

Mesmo desenho de `user_mapper`: tupla, e não objeto, porque é o formato que as
tabelas desta aplicação já desenham, e porque assim o adaptador de banco e o
de demonstração entregam a MESMA coisa — trocar a fonte não vira refatoração
de widget.

Três decisões que a tupla carrega:

- **`id` na primeira posição, não escondido.** Confirmar e cancelar recebem o
  identificador da movimentação; sem ele na linha, a tela teria que manter um
  índice paralelo entre o que desenhou e o que leu, e qualquer reordenação
  passaria a confirmar a linha errada.
- **`quantidade` é um inteiro POSITIVO.** O sinal mora na espécie
  (`MovementKind.sinal`), como na tabela, que tem `CHECK (quantity > 0)`.
  Devolver um inteiro com sinal aqui colocaria a mesma informação em duas
  colunas, e somar a coluna de quantidade passaria a depender de qual das
  duas se lê.
- **código e nome vêm de FORA.** A linha traz `product_id` (uuid) e a tela
  precisa de código e nome, que moram em `products`. Resolver um a um daria
  N+1 — uma ida à rede por movimentação para abrir a tela. Quem chama resolve
  em lote e passa pronto, exatamente como `row_to_product` faz com a
  categoria.
"""

from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.movement_status import MovementStatus
from stockflow.domain.stock_adjustment import saldo_contado
from stockflow.domain.stock_level import to_int
from stockflow.infrastructure.repositories.user_mapper import (
    NUNCA,
    formatar_ultimo_acesso,
)

# O que a tela escreve numa célula sem valor. Mesmo travessão que
# `row_to_user` usa para departamento ausente, para que as duas tabelas não
# marquem a mesma ausência de jeitos diferentes.
VAZIO = "—"


def formatar_quando(valor, agora=None) -> str:
    """"Hoje, 09:14" / "Ontem, 17:30" / "12/08/2026".

    Delega a `formatar_ultimo_acesso` em vez de repetir o critério: as duas
    telas respondem à mesma pergunta ("quando foi isso?") e duas cópias da
    regra divergiriam na primeira mudança de formato. O que muda é só o
    fallback — "Nunca" é uma resposta sobre acesso, não sobre um carimbo que
    a coluna `created_on NOT NULL` garante existir; aqui um valor ilegível é
    ausência de informação, não um evento que não aconteceu.

    `agora` é parâmetro pelo mesmo motivo de lá: com `datetime.now()`
    embutido, o teste de "Hoje" passaria hoje e falharia na virada do dia, e
    o resultado dependeria do fuso da máquina que rodasse a suíte.
    """
    texto = formatar_ultimo_acesso(valor, agora)
    return VAZIO if texto == NUNCA else texto


def _rotulo_de_especie(valor) -> str:
    """Rótulo da espécie, tolerando valor que o enum não conhece.

    Um `kind` desconhecido só chega aqui se o banco ganhar um valor novo no
    enum antes da aplicação — e nesse dia é melhor a tabela mostrar o valor
    cru numa linha do que derrubar a listagem inteira.
    """
    try:
        return MovementKind.from_value(valor).label
    except ValueError:
        return str(valor or VAZIO)


def _rotulo_de_situacao(valor) -> str:
    try:
        return MovementStatus.from_value(valor).label
    except ValueError:
        return str(valor or VAZIO)


def _rotulo_de_motivo(valor) -> str:
    """Rótulo do motivo do ajuste, ou travessão quando não é ajuste.

    Mesma tolerância de `_rotulo_de_especie`: valor que o enum ainda não
    conhece aparece cru numa célula em vez de derrubar a listagem inteira.
    """
    if not valor:
        return VAZIO
    try:
        return AdjustmentReason.from_value(valor).label
    except ValueError:
        return str(valor)


def row_to_movement(row, product_code="", product_name="", agora=None,
                    supplier_name="") -> tuple:
    """Linha de `stock_movements` na tupla que a tabela desenha.

    DEZ posições, SEMPRE. A cauda já foi opcional — o fornecedor só entrava
    quando existia — e a tela lia `mov[8] if len(mov) > 8`. Com duas caudas
    opcionais o motivo do ajuste ocuparia o índice do fornecedor sempre que o
    produto não tivesse um, e "Quebra / avaria" apareceria na coluna errada.
    Ausência é travessão, como em toda célula vazia desta aplicação.

    `product_code` e `product_name` chegam de fora porque moram em
    `products`; ver a nota de N+1 no topo do módulo.
    """
    return (
        row.get("id"),
        product_code or VAZIO,
        product_name or VAZIO,
        _rotulo_de_especie(row.get("kind")),
        to_int(row.get("quantity")),
        _rotulo_de_situacao(row.get("status")),
        (str(row.get("note") or "").strip() or VAZIO),
        formatar_quando(row.get("created_on"), agora),
        supplier_name or VAZIO,
        _rotulo_de_motivo(row.get("adjustment_reason")),
    )


def rows_to_movements(rows, produtos=None, agora=None, fornecedores=None) -> tuple:
    """Várias linhas, resolvendo o produto por um mapa `id -> (código, nome)`.

    Produto não encontrado no mapa vira travessão em vez de erro: a RLS de
    `products` pode filtrar o que a de `stock_movements` deixou passar (linha
    de outra empresa, produto removido em cascata), e essa combinação é
    informação faltando numa célula, não motivo para a tela não abrir.
    """
    produtos = produtos or {}
    fornecedores = fornecedores or {}
    resultado = []
    for row in rows or ():
        supplier_id = row.get("supplier_id")
        resultado.append(row_to_movement(
            row,
            *produtos.get(row.get("product_id"), ("", "")),
            agora=agora,
            supplier_name=(
                fornecedores.get(supplier_id, "Fornecedor indisponível")
                if supplier_id else ""
            ),
        ))
    return tuple(resultado)


def movement_input_to_register_args(data, company_id, product_id) -> dict:
    """Argumentos nomeados de `fn_register_movement`.

    `p_company_id` VAI junto, ao contrário de `fn_update_products`: a função
    o usa para checar `fn_has_role` e para exigir que o produto seja DAQUELA
    empresa. É o par (empresa, produto) que fecha o buraco — informar uma
    empresa onde se tem alçada não dá acesso a produto de outra.

    `created_by` não entra: quem registra é a sessão, e a função resolve por
    `fn_current_user_id()`. Ver a nota em `MovementInput`.

    Nota vazia vira NULL, e não string vazia: a coluna é nullable e "não
    escrevi nota" é ausência. Gravar `''` faria um filtro por nota preenchida
    encontrar movimentações sem nota nenhuma.
    """
    nota = str(getattr(data, "note", "") or "").strip()
    args = {
        "p_company_id": company_id,
        "p_product_id": product_id,
        "p_kind": MovementKind.from_value(data.kind).value,
        # Inteiro, não texto: a função compara `p_quantity <= 0` e a coluna é
        # `integer`.
        "p_quantity": to_int(data.quantity),
        "p_note": nota or None,
        "p_confirm": bool(getattr(data, "confirm", False)),
    }
    if getattr(data, "supplier_id", None):
        args["p_supplier_id"] = data.supplier_id
    return args


def adjustment_input_to_args(data, company_id, product_id) -> dict:
    """Argumentos nomeados de `fn_register_adjustment`.

    `p_expected_balance` vai junto e a CHAVE não é opcional: é o saldo que a
    tela exibiu, e é ele que faz a função recusar quando outra pessoa
    movimentou o produto no meio. Omitir a chave transformaria "esqueci de
    passar" em "não quero a checagem de concorrência".

    O VALOR, porém, preserva `None` como `None` (NULL), em vez de passar por
    `to_int` — a função só pula a checagem quando recebe NULL de verdade
    (`IF p_expected_balance IS NOT NULL AND p_expected_balance <> v_current`
    em `fn_register_adjustment`), e é assim que o adaptador de demonstração
    também lê (`if esperado is not None and ...`). Rodar `to_int(None)` aqui
    gravaria `0`, e todo ajuste sem saldo esperado passaria a recusar com
    "na tela: 0, agora: <o saldo real>" em vez de pular a checagem como os
    dois adaptadores atrás da mesma porta precisam concordar em fazer.

    `p_counted_balance`, ao contrário, passa por `saldo_contado`, que
    LEVANTA — nunca por `to_int`. Os dois parâmetros parecem simétricos e não
    são: NULL no esperado significa "não quero a checagem de concorrência",
    uma opção documentada, enquanto um contado ausente não significa nada.
    `to_int(None)` devolveria `0` — que não chega ao banco como NULL, chega
    como uma contagem válida de zero e esvazia o produto. Para o número que
    decide quanto estoque sai, o padrão certo é não ter padrão.

    Detalhe vazio vira NULL, não string vazia, pelo mesmo motivo da nota em
    `movement_input_to_register_args`.
    """
    detalhe = str(getattr(data, "detail", "") or "").strip()
    esperado = data.expected_balance
    return {
        "p_company_id": company_id,
        "p_product_id": product_id,
        "p_counted_balance": saldo_contado(data.counted_balance),
        "p_expected_balance": None if esperado is None else to_int(esperado),
        "p_reason": AdjustmentReason.from_value(data.reason).value,
        "p_detail": detalhe or None,
    }
