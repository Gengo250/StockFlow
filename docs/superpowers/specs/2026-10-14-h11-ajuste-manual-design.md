# H11 — Ajuste manual de estoque

Fluxo de ajuste manual de inventário, com validação de permissão, de
justificativa e do saldo resultante.

Data: 2026-10-14

## História

O responsável pelo estoque conta fisicamente um produto, encontra um número
diferente do que o sistema mostra e corrige o saldo informando o valor
contado e o motivo da divergência. O sistema recusa quem não tem alçada,
recusa ajuste sem justificativa e garante que o saldo final seja exatamente o
contado.

## Critérios de aceitação

1. **Permissão.** Apenas `ADMIN` e `STOCK` ajustam estoque. O `SELLER` é
   recusado na aplicação e no banco, independentemente de a tela esconder o
   controle.
2. **Justificativa.** Todo ajuste grava um motivo de lista fechada. O motivo
   `OUTRO` exige texto descritivo; sem ele, nada é gravado.
3. **Saldo resultante.** Depois do ajuste, o saldo do produto é exatamente o
   valor contado — verificado dentro da mesma transação que grava.

## Decisões de desenho

### Semântica: saldo contado, não delta

O operador informa o saldo **contado**, e o sistema deriva o lançamento. A
alternativa (informar `+N`/`−N`) foi descartada porque esvazia o terceiro
critério: com delta, o saldo resultante é consequência aritmética do que foi
digitado, e "validar o saldo resultante" não teria o que validar. Com
contagem, o número final é uma afirmação do usuário que a transação confere.

### O ajuste não é uma terceira espécie de movimentação

`domain/enums/movement_kind.py` já registra a decisão: *"Ajuste não é uma
terceira espécie: é uma entrada ou uma saída com justificativa na nota."* Um
`AJUSTE` de quantidade com sinal exigiria derrubar o `CHECK (quantity > 0)`
de `stock_movements`, reescrever o `CASE` de `fn_confirmed_balance`, o
`.sinal` do enum, o `_aplicar_no_saldo` do adaptador de demonstração e todos
os testes que assumem duas espécies.

Um ajuste é, portanto, uma movimentação `ENTRADA` ou `SAIDA` comum, já
`CONFIRMADA`, distinguida por `adjustment_reason IS NOT NULL`.

### Tabela de auditoria separada foi descartada

`role_change_log` e `price_edit_log` existem porque mudança de papel e de
preço **sobrescrevem** o valor anterior — sem a tabela não sobra rastro. Um
ajuste deixa uma linha imutável em `stock_movements`, então o rastro já
existe. `counted_balance` entra como coluna na própria movimentação, não como
tabela: permite que um relatório de reconciliação reconfira a invariante
depois, em vez de confiar que ela foi checada na gravação.

### Operação atômica, sem ciclo pendente → confirmada

Contagem é uma afirmação sobre **agora**. Um ajuste pendente confirmado meia
hora depois aplicaria uma diferença calculada sobre um saldo que já mudou, e
o saldo final não seria o contado. A função grava já confirmada, numa
transação.

### Concorrência: o saldo da tela faz parte do pedido

Entre a tela carregar e o usuário clicar, outra pessoa pode movimentar o mesmo
produto. A função recebe `p_expected_balance` — o saldo que a tela exibiu — e
**recusa** quando ele não bate com o real, pedindo recontagem.

Recalcular silenciosamente seria pior: se alguém confirmou uma entrada de 3 e
colocou 3 unidades na prateleira, o saldo correto é 41, não os 38 que foram
contados antes. Nenhum dos dois números é confiável sem uma nova contagem.

### Lugar na interface

Segundo card dentro de Movimentações, não tela nova. O histórico já está logo
abaixo, a área `movimentacoes` da matriz de permissão é reaproveitada (as
chaves da matriz são as mesmas do menu lateral, então tela nova significaria
área nova) e o menu não cresce.

## Arquitetura

```
MovimentacoesPage.adjust_requested(AdjustmentInput)
  └─ MainWindow._aplicar_ajuste
      └─ MovementService.adjust(session, data)       permissão + validação local
          └─ MovementRepository.adjust(data)          porta
              ├─ DemoMovementRepository.adjust        imita a função SQL
              └─ SupabaseMovementRepository.adjust    rpc fn_register_adjustment
```

### Domínio

`domain/enums/adjustment_reason.py` — `AdjustmentReason(StrEnum)` espelhando
`public.adjustment_reason`, no mesmo formato de `MovementKind`:

| Valor | Rótulo |
|---|---|
| `CONTAGEM` | Erro de contagem |
| `QUEBRA` | Quebra / avaria |
| `PERDA` | Perda / furto |
| `VENCIMENTO` | Vencimento |
| `DEVOLUCAO` | Devolução de cliente |
| `OUTRO` | Outro |

Com `.label`, `.from_value()` e `.exige_detalhe` (verdadeiro só para `OUTRO`).

`domain/stock_adjustment.py` — a aritmética do ajuste, com um dono só:

```python
def calcular_ajuste(saldo_atual: int, contado: int) -> tuple[MovementKind, int]
```

Contado maior devolve `(ENTRADA, diferença)`; menor, `(SAIDA, diferença)`;
igual levanta `AjusteSemEfeitoError`. Contado negativo levanta `ValueError`.

A tela usa essa função para a prévia ao vivo e o serviço para validar antes da
rede. Duas cópias da regra é como a UI e `fn_stock_state` divergiram em 5 de
11 casos antes da US03.

### Banco

Em `database/code/tables/05_movements.sql`, inline no `CREATE TABLE` — o tipo
nasce no mesmo arquivo e não há dependência de arquivo posterior, ao
contrário de `supplier_id` (07) e `sale_id` (06), que precisaram de `ALTER`:

```sql
CREATE TYPE public.adjustment_reason AS ENUM
    ('CONTAGEM', 'QUEBRA', 'PERDA', 'VENCIMENTO', 'DEVOLUCAO', 'OUTRO');

    adjustment_reason public.adjustment_reason,
    counted_balance   integer CHECK (counted_balance >= 0),

    CONSTRAINT ck_movements_adjustment_pair CHECK (
        (adjustment_reason IS NULL     AND counted_balance IS NULL)
     OR (adjustment_reason IS NOT NULL AND counted_balance IS NOT NULL)),

    CONSTRAINT ck_movements_adjustment_detail CHECK (
        adjustment_reason IS DISTINCT FROM 'OUTRO'
     OR btrim(coalesce(note, '')) <> '')
```

O segundo CHECK é o que torna a justificativa regra do banco: `OUTRO` sem
texto é recusado mesmo por quem chame a função direto por SQL. Os demais
motivos dispensam CHECK — motivo inválido já é erro de tipo.

Índice parcial, no molde de `idx_stock_movements_supplier`:

```sql
CREATE INDEX idx_stock_movements_adjustment
    ON public.stock_movements (company_id, created_on)
    WHERE adjustment_reason IS NOT NULL;
```

Em `database/code/procedures/04a_movements.sql`:

```sql
fn_register_adjustment(
    p_company_id uuid, p_product_id uuid,
    p_counted_balance integer, p_expected_balance integer,
    p_reason public.adjustment_reason, p_detail text DEFAULT NULL
) RETURNS uuid   -- plpgsql, VOLATILE, SECURITY DEFINER, search_path = public
```

Ordem das verificações e o erro de cada uma:

| Passo | SQLSTATE |
|---|---|
| `fn_has_role(p_company_id, ARRAY['ADMIN','STOCK'])` | `insufficient_privilege` |
| `p_counted_balance` não nulo e `>= 0` | `check_violation` |
| `p_reason` não nulo; `OUTRO` com `p_detail` não vazio | `check_violation` |
| produto da empresa e ativo, lido com `FOR UPDATE` | `foreign_key_violation` |
| `p_expected_balance` igual ao saldo real (quando informado) | `serialization_failure` |
| `p_counted_balance` diferente do saldo atual | `check_violation` |
| `INSERT` já `CONFIRMADA`, `created_by = fn_current_user_id()` | — |
| relê `products.stock` e confere igual ao contado | `check_violation` |

O `FOR UPDATE` serializa dois ajustes do mesmo produto. A releitura final é o
terceiro critério: o trigger `trg_stock_movements_apply` já rodou quando o
`INSERT` terminou, então ou `products.stock` é exatamente o contado, ou a
transação inteira volta atrás.

A função também atualiza `products.last_updated_by`, como `fn_edit_product_stock`.

`p_expected_balance` aceita `NULL` mas **não tem `DEFAULT`**: fica antes de
`p_reason` na assinatura, então todo chamador o informa, nem que seja como
`NULL` — e `NULL` pula a checagem de concorrência. A tela sempre envia o
saldo que exibiu. Deixá-lo com `DEFAULT NULL` transformaria "esqueci de
passar" em "não quero a checagem", que é o modo de falhar caro.

Em `database/code/policies/01_security.sql`, `fn_register_adjustment` entra na
allowlist de `EXECUTE` (linha ~192). Sem isso o SQL aplica e o app quebra em
runtime por falta de privilégio; o bloco `DO` do arquivo levanta exceção se o
nome não existir.

Migration `database/supabase/migrations/<ts>_h11_manual_stock_adjustment.sql`,
com `<ts>` no formato `YYYYMMDDHHMMSS` e estritamente maior que
`20261013140000`, a última da cadeia. Abre `BEGIN`/`COMMIT` próprios
(convenção fixada em b92c490) e é idempotente em tipo, colunas, constraints e
índice. O remoto já divergiu do repositório uma
vez, então ela precisa aplicar sobre um banco que pode ter parte disso.

### Aplicação

`application/dto/adjustment_input.py`:

```python
@dataclass(frozen=True)
class AdjustmentInput:
    product_code: str
    counted_balance: int
    expected_balance: int
    reason: AdjustmentReason
    detail: str = ""
```

Sem `created_by`, pela mesma razão de `MovementInput`: autoria sai de
`fn_current_user_id()`; aceitar da tela deixaria registrar ajuste em nome de
outra pessoa.

`application/ports/movement_repository.py` ganha `adjust(data) -> str`.

`MovementService.adjust(session, data)` chama
`ensure_can_move_stock(session, action="ajustar o estoque")` **antes de tocar
no repositório** e valida o que não precisa de rede: produto ativo, contado
não negativo, motivo conhecido, `OUTRO` com detalhe, diferença não nula.
Nenhuma substitui a do banco — são as que dão mensagem em português sem
gastar requisição.

O rótulo `"ajustar o estoque"` entra também em `ACTION_BY_RPC` do adaptador
Supabase, que o usa para traduzir `42501` em `PermissionDeniedError`. Rótulos
iguais nas duas camadas é o que faz divergência entre elas aparecer como
divergência, e não como "outro erro".

### Infraestrutura

`DemoMovementRepository.adjust` imita a função SQL passo a passo: produto
existente e ativo, `expected_balance` conferido contra o saldo real do dict,
diferença calculada por `calcular_ajuste`, linha `CONFIRMADA` com
`adjustment_reason` e `counted_balance`, e asserção final de que o saldo do
produto ficou igual ao contado.

`SupabaseMovementRepository.adjust` traduz código em uuid pelo cache já
existente e chama a rpc. `MOVEMENT_COLUMNS` passa a incluir
`adjustment_reason` e `counted_balance`. `movement_mapper` ganha
`adjustment_input_to_args`.

### Conserto de escopo: a tupla do histórico

`rows_to_movements` hoje só acrescenta o fornecedor **quando existe**, e a
tela lê `mov[8] if len(mov) > 8 else "—"`. Pendurar o motivo no fim disso
colocaria o motivo no índice 8 sempre que o produto não tivesse fornecedor —
"Quebra / avaria" apareceria na coluna Fornecedor. A maioria das saídas não
tem fornecedor, então não é risco teórico.

A tupla passa a ter comprimento **fixo de 10**, ausência virando `—` como em
toda célula vazia desta aplicação:

```
(id, código, nome, espécie, quantidade, situação, observação, quando,
 fornecedor, motivo)
```

Toca `row_to_movement`, os dois adaptadores e os testes que leem as tuplas.

### Apresentação

Segundo card em `pages/movimentacoes.py`, abaixo do de entrada/saída:

```
┌─ Ajuste manual de inventário ───────────────────────────────┐
│ [produto ▾]   Saldo atual: 42   Contado: [38]  → SAÍDA de 4 │
│ [motivo ▾]  [detalhe]                            [Aplicar]  │
└─────────────────────────────────────────────────────────────┘
```

- **Saldo atual** vem do mesmo dict `self.products` que o Estoque desenha —
  a identidade que já existe, não uma cópia. Produto desativado sai da oferta
  na hora, como nas demais telas.
- **`→ SAÍDA de 4`** é `calcular_ajuste` a cada tecla. Contado igual ao atual
  mostra "Sem diferença" e desabilita *Aplicar*.
- **Detalhe** fica obrigatório quando o motivo é `Outro`, com o placeholder
  mudando junto.
- A tabela ganha a coluna **Motivo**, simétrica a Fornecedor: `—` quando não
  é ajuste. O saldo contado vai no tooltip da célula ("Saldo contado: 38").
  A coluna **Espécie** continua pura — `Entrada` ou `Saída`, sem sufixo: o
  que distingue um ajuste é a coluna Motivo estar preenchida, e repetir a
  informação nas duas faria as duas poderem discordar.
- `apply_permission` passa a desabilitar também os controles do card novo.
  Continua sendo cortesia: quem recusa de verdade é o serviço e o banco.

Sinal novo: `adjust_requested = Signal(object)`, carregando `AdjustmentInput`.

`MainWindow._aplicar_ajuste` segue `_registrar_movimentacao`:
`PermissionDeniedError` e `ValueError` viram `mostrar_recusa` no próprio card,
nunca diálogo. No sucesso, limpa o formulário e recarrega Movimentações **e**
Estoque — ajuste muda saldo, saldo muda situação, e alerta desatualizado é o
que a US04 proíbe.

`serialization_failure` ganha tratamento próprio: não é erro do usuário nem
falha do sistema, é pedido de recontagem. A mensagem diz o saldo que a tela
mostrou e o saldo real agora, e a tela recarrega o catálogo para que "Saldo
atual" já exiba o número novo.

## Testes

`tests/test_h11_ajuste_manual.py` — caminho do usuário, janela real em
offscreen, no molde de `test_h14_perfis_e_permissoes.py`:

| Critério | Teste | Prova |
|---|---|---|
| Permissão | SELLER: card desabilitado; `MovementService.adjust` levanta `PermissionDeniedError` | a recusa não depende do botão escondido |
| Justificativa | motivo `Outro` sem detalhe: recusa com mensagem e nenhuma linha gravada | justificativa é condição de gravação |
| Saldo resultante | STOCK conta 38 sobre 42: `products["X"].stock == "38"`, e a linha nova do histórico traz Espécie `Saída`, Quantidade `4`, Motivo `Quebra / avaria` | o saldo final é o contado |

Mais: contado igual ao atual (Aplicar desabilitado **e** serviço recusa),
contado `0` sobre saldo 5 (saída de 5, resultante zero — ajuste válido), e
`expected_balance` defasado (recusa pedindo recontagem).

Demais arquivos:

- `tests/unit/test_stock_adjustment.py` — `calcular_ajuste` nos quatro
  quadrantes, isolada de Qt e de banco.
- `tests/unit/test_movement_repositories.py` — estendido: os dois adaptadores
  satisfazem `adjust` com a mesma semântica e devolvem a tupla de 10
  posições. É o teste que impede o modo demonstração de divergir do banco.
- `tests/unit/test_permission_matrix.py` — passa a cobrir
  `fn_register_adjustment` além de `fn_register_movement`. Sem isso, alguém
  afrouxa a função nova para `fn_is_member` e nenhum teste nota.
- `tests/test_database_migrations.py` — seção H11: tipo criado antes do uso,
  colunas declaradas, os dois CHECKs presentes, função na allowlist,
  timestamp em ordem.
- `tests/test_schema_declarativo.py` — já cobre o espelho `code/` ↔
  `schemas/`; precisa apenas dos dois lados sincronizados.

## Verificação

Teste com cliente Supabase falso não prova schema. `scripts/verify_postgres.py`
ganha um bloco H11 e roda nos dois modos:

```bash
QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q
uv run python scripts/verify_postgres.py            # database/supabase/migrations
uv run python scripts/verify_postgres.py --schema   # database/code
```

Os dois modos precisam passar: há bugs que só quebram o declarativo, e
comparar os caminhos é o que prova que a migration é fiel à fonte.

O bloco H11 exercita o que só o Postgres decide: `insufficient_privilege`
para SELLER, `check_violation` para `OUTRO` sem detalhe,
`serialization_failure` para saldo defasado, e `products.stock` relido por
conexão independente valendo exatamente o contado.

A máquina não tem `postgres` no PATH. Vale a receita já registrada: pacote
`pgserver`, cópia descartável do `pginstall` no scratchpad, stub de `pgcrypto`
na cópia, `LD_LIBRARY_PATH` apontando para `pgserver.libs` e socket em `/tmp`
curto. **O stub não testa criptografia**, e isso entra no relatório.

**Ensaio incremental.** O remoto já divergiu do repositório — tem
`sales`/`sale_items` que a cadeia de migrations não descreve. Aplicar em banco
limpo não prova `supabase db push`. O ensaio corta as migrations por
timestamp, aplica as anteriores, insere movimentações preexistentes e só então
aplica a da H11 — é assim que se descobre se `ADD COLUMN` com CHECK quebra
sobre dado existente. Antes, sondar o remoto (`42501` versus `42703`) para
saber se alguma dessas colunas já está lá.

**Regressão visual.** O card novo muda o layout de Movimentações, então o
baseline de `scripts/check_visual.py` para essa página muda de propósito:
capturar antes, capturar depois, apresentar o diff como mudança aceita, sem
silenciar o código de saída.

## Entrega

Branch `feat/h11-manual-stock-adjustment`; commits, título e corpo de PR em
inglês. PR, não push direto — a `main` exige pull request, e push direto só
passa por bypass do dono. Nada commitado, empurrado ou mesclado sem o usuário
confirmar o diff e a mensagem.

A migration é entregue ensaiada, com o comando para o usuário rodar:

```bash
cd database && supabase link --project-ref "$SUPABASE_PROJECT_REF" && supabase db push
```

Quem aplica no Supabase é o usuário.

O README ganha a descrição do ajuste manual na seção de Movimentações.

## Fora de escopo

- **Ajuste em lote** (inventário de vários produtos de uma vez).
- **Relatório de ajustes** por motivo e período — o índice parcial é o que o
  deixa barato quando vier.
- **Estorno de ajuste**: cancelar um ajuste já funciona pelo caminho genérico
  de `fn_cancel_movement`, que devolve o saldo.
- **Teto de quantidade por papel** (STOCK ajusta até N, acima só ADMIN):
  descartado por introduzir um número de configuração que o banco também
  precisaria conhecer.
