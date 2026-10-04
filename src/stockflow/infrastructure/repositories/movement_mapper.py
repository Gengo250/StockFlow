"""Tradução entre a linha de `public.stock_movements` e a linha da tela.

A tabela de Movimentações consome tuplas neste contrato:

    (id, código, nome do produto, espécie, quantidade, situação, nota, quando)

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

from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.movement_status import MovementStatus
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


def row_to_movement(row, product_code="", product_name="", agora=None) -> tuple:
    """Linha de `stock_movements` na tupla que a tabela desenha.

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
    )


def rows_to_movements(rows, produtos=None, agora=None) -> tuple:
    """Várias linhas, resolvendo o produto por um mapa `id -> (código, nome)`.

    Produto não encontrado no mapa vira travessão em vez de erro: a RLS de
    `products` pode filtrar o que a de `stock_movements` deixou passar (linha
    de outra empresa, produto removido em cascata), e essa combinação é
    informação faltando numa célula, não motivo para a tela não abrir.
    """
    produtos = produtos or {}
    return tuple(
        row_to_movement(row, *produtos.get(row.get("product_id"), ("", "")), agora=agora)
        for row in rows or ()
    )


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
    return {
        "p_company_id": company_id,
        "p_product_id": product_id,
        "p_kind": MovementKind.from_value(data.kind).value,
        # Inteiro, não texto: a função compara `p_quantity <= 0` e a coluna é
        # `integer`.
        "p_quantity": to_int(data.quantity),
        "p_note": nota or None,
        "p_confirm": bool(getattr(data, "confirm", False)),
    }
