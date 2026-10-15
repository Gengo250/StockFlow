# H11 — Ajuste manual de estoque: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** permitir que ADMIN e STOCK corrijam o saldo de um produto informando
o valor contado e um motivo, com o saldo final garantidamente igual ao contado.

**Architecture:** um ajuste é uma movimentação `ENTRADA`/`SAIDA` comum, já
`CONFIRMADA`, distinguida pela coluna `adjustment_reason`. Uma única função
`SECURITY DEFINER` (`fn_register_adjustment`) faz tudo numa transação: checa
papel, trava o produto, calcula a diferença, grava e relê o saldo para
confirmar que bateu com o contado. Nada muda no caminho que compõe o saldo —
nem o enum de espécie, nem `fn_confirmed_balance`, nem o trigger.

**Tech Stack:** Python 3.12, PySide6, PostgreSQL/Supabase, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-10-14-h11-ajuste-manual-design.md`

## Global Constraints

- **Papéis autorizados:** `ADMIN` e `STOCK`. `SELLER` é recusado na aplicação
  e no banco.
- **Motivos válidos** (valores exatos do enum): `CONTAGEM`, `QUEBRA`, `PERDA`,
  `VENCIMENTO`, `DEVOLUCAO`, `OUTRO`. Só `OUTRO` exige detalhe escrito.
- **Comentários de código em português**, como todo o resto do repositório.
  **Artefatos de Git em inglês**: nome de branch, mensagens de commit, título
  e corpo de PR.
- **Branch:** `feat/h11-manual-stock-adjustment`. Nunca commitar na `main`:
  ela exige pull request.
- **Nunca aplicar migration no Supabase remoto.** A entrega é a migration
  ensaiada localmente mais o comando para o usuário rodar.
- **Nada de `git push` nem `gh pr create` sem o usuário confirmar** o diff e a
  mensagem.
- **Suíte completa:** `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q`
  — sempre com o caminho `tests/`; `pytest` sem argumento varre `scripts/` e
  tenta coletar um teste que fala com a rede.
- **Fonte declarativa do banco é `database/code/`.** Toda edição lá precisa
  ser espelhada em `database/supabase/schemas/<mesmo caminho>`. Editar só o
  espelho é perda silenciosa: o próximo `sync_schemas()` sobrescreve.

---

### Task 1: Domínio — motivo do ajuste e aritmética da contagem

**Files:**
- Create: `src/stockflow/domain/enums/adjustment_reason.py`
- Create: `src/stockflow/domain/stock_adjustment.py`
- Create: `src/stockflow/domain/exceptions/adjustment_errors.py`
- Test: `tests/unit/test_stock_adjustment.py`

**Interfaces:**
- Consumes: `stockflow.domain.enums.movement_kind.MovementKind` (já existe,
  com `.sinal` e `.from_value`).
- Produces:
  - `AdjustmentReason(StrEnum)` com membros `CONTAGEM`, `QUEBRA`, `PERDA`,
    `VENCIMENTO`, `DEVOLUCAO`, `OUTRO`; propriedades `.label -> str` e
    `.exige_detalhe -> bool`; classmethod `.from_value(valor) -> AdjustmentReason`.
  - `calcular_ajuste(saldo_atual: int, contado: int) -> tuple[MovementKind, int]`
  - `AjusteSemEfeitoError(ValueError)`
  - `SaldoDesatualizadoError(ValueError)` com
    `.de_saldos(esperado: int, atual: int) -> SaldoDesatualizadoError`

- [ ] **Step 0: Create the branch**

```bash
git switch -c feat/h11-manual-stock-adjustment
```

Nunca trabalhe na `main`: ela exige pull request.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_stock_adjustment.py`:

```python
"""A aritmética do ajuste manual tem um dono só (H11).

A tela mostra "→ SAÍDA de 4" enquanto o usuário digita e o serviço valida o
mesmo antes de ir à rede. Se cada um calculasse por conta própria, seria a
repetição que fez a UI divergir de `fn_stock_state` em 5 de 11 casos antes
da US03 — a tela dizia `Crítico` onde o SQL dizia `Baixo`.
"""

import pytest

from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.exceptions.adjustment_errors import (
    AjusteSemEfeitoError,
    SaldoDesatualizadoError,
)
from stockflow.domain.stock_adjustment import calcular_ajuste


def test_contado_maior_vira_entrada_da_diferenca():
    assert calcular_ajuste(42, 50) == (MovementKind.ENTRADA, 8)


def test_contado_menor_vira_saida_da_diferenca():
    assert calcular_ajuste(42, 38) == (MovementKind.SAIDA, 4)


def test_contar_zero_sobre_saldo_positivo_e_ajuste_valido():
    """Zerar o saldo é ajuste legítimo, não erro de digitação.

    É o caso do produto que sumiu inteiro da prateleira, e a saída de 5
    deixa o saldo em zero — dentro do `CHECK (stock >= 0)` de `products`.
    """
    assert calcular_ajuste(5, 0) == (MovementKind.SAIDA, 5)


def test_contado_igual_ao_atual_nao_gera_movimentacao():
    """Diferença zero não vira linha: `CHECK (quantity > 0)` a recusaria.

    Recusar aqui, com nome próprio, é o que permite à tela desabilitar o
    botão antes do clique em vez de traduzir um erro do Postgres.
    """
    with pytest.raises(AjusteSemEfeitoError):
        calcular_ajuste(42, 42)


def test_contado_negativo_e_recusado():
    with pytest.raises(ValueError):
        calcular_ajuste(42, -1)


def test_so_outro_exige_detalhe():
    assert AdjustmentReason.OUTRO.exige_detalhe is True
    assert [r for r in AdjustmentReason if r.exige_detalhe] == [AdjustmentReason.OUTRO]


def test_motivo_desconhecido_estoura_com_o_valor_na_mensagem():
    with pytest.raises(ValueError, match="INVENTADO"):
        AdjustmentReason.from_value("INVENTADO")


def test_motivo_aceita_o_proprio_enum_e_texto_cru():
    assert AdjustmentReason.from_value("quebra") is AdjustmentReason.QUEBRA
    assert AdjustmentReason.from_value(AdjustmentReason.PERDA) is AdjustmentReason.PERDA


def test_saldo_desatualizado_diz_os_dois_numeros():
    erro = SaldoDesatualizadoError.de_saldos(esperado=42, atual=45)

    assert "42" in str(erro) and "45" in str(erro)
    assert isinstance(erro, ValueError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_stock_adjustment.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'stockflow.domain.enums.adjustment_reason'`

- [ ] **Step 3: Write the enum**

Create `src/stockflow/domain/enums/adjustment_reason.py`:

```python
"""Motivo de um ajuste manual de inventário, espelhando `public.adjustment_reason`."""

from enum import StrEnum


class AdjustmentReason(StrEnum):
    """Lista fechada, e não texto livre.

    "Quanto sumiu por quebra neste mês" precisa ser consulta, não leitura de
    observações — e motivo inválido vira erro de TIPO no Postgres, que é a
    recusa mais barata que existe. O texto descritivo continua existindo em
    `note`, como detalhe do motivo, nunca como substituto dele.
    """

    CONTAGEM = "CONTAGEM"
    QUEBRA = "QUEBRA"
    PERDA = "PERDA"
    VENCIMENTO = "VENCIMENTO"
    DEVOLUCAO = "DEVOLUCAO"
    OUTRO = "OUTRO"

    @property
    def label(self) -> str:
        return {
            AdjustmentReason.CONTAGEM: "Erro de contagem",
            AdjustmentReason.QUEBRA: "Quebra / avaria",
            AdjustmentReason.PERDA: "Perda / furto",
            AdjustmentReason.VENCIMENTO: "Vencimento",
            AdjustmentReason.DEVOLUCAO: "Devolução de cliente",
            AdjustmentReason.OUTRO: "Outro",
        }[self]

    @property
    def exige_detalhe(self) -> bool:
        """`OUTRO` sem texto não diz nada — é o motivo que não é motivo.

        Espelha o CHECK `ck_movements_adjustment_detail` da tabela, para que
        a tela recuse antes de gastar a requisição que o banco recusaria.
        """
        return self is AdjustmentReason.OUTRO

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Motivo de ajuste inválido: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Motivo de ajuste desconhecido: {value!r}") from None
```

- [ ] **Step 4: Write the exceptions**

Create `src/stockflow/domain/exceptions/adjustment_errors.py`:

```python
"""Recusas nomeadas do ajuste manual (H11).

As duas herdam de `ValueError` de propósito: `MainWindow` já trata
`ValueError` como "recusa que o usuário lê no card", e herdar mantém o
comportamento correto mesmo onde ninguém escreveu um `except` específico.
"""


class AjusteSemEfeitoError(ValueError):
    """Contado igual ao saldo atual: não há diferença a lançar."""

    def __init__(self, saldo: int):
        self.saldo = saldo
        super().__init__(
            f"O saldo contado é igual ao saldo atual ({saldo}). "
            "Não há ajuste a registrar."
        )


class SaldoDesatualizadoError(ValueError):
    """O saldo mudou entre a contagem e a gravação.

    Não é erro do usuário nem falha do sistema: é pedido de recontagem. Se
    alguém confirmou uma entrada e pôs a mercadoria na prateleira, nem o
    número contado antes nem o saldo de agora descrevem o que está lá.
    """

    @classmethod
    def de_saldos(cls, esperado: int, atual: int) -> "SaldoDesatualizadoError":
        return cls(
            f"O saldo mudou desde a contagem (na tela: {esperado}, agora: "
            f"{atual}). Reconte o produto antes de ajustar."
        )
```

- [ ] **Step 5: Write the arithmetic**

Create `src/stockflow/domain/stock_adjustment.py`:

```python
"""Aritmética do ajuste manual de inventário (H11).

O operador informa o saldo CONTADO e o sistema deriva o lançamento. Esta
função é a tradução literal do `IF p_counted_balance > v_current` de
`fn_register_adjustment`, e existe para que a prévia da tela e a validação
do serviço não sejam duas contas que podem discordar.
"""

from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.exceptions.adjustment_errors import AjusteSemEfeitoError


def calcular_ajuste(saldo_atual: int, contado: int) -> tuple[MovementKind, int]:
    """Espécie e quantidade POSITIVA que levam `saldo_atual` até `contado`.

    Quantidade positiva, com o sinal morando na espécie: é o mesmo contrato
    de `stock_movements`, que tem `CHECK (quantity > 0)`. Devolver um
    inteiro com sinal colocaria a mesma informação em dois lugares.
    """
    saldo_atual = int(saldo_atual)
    contado = int(contado)

    if contado < 0:
        raise ValueError(f"O saldo contado não pode ser negativo (recebido: {contado}).")
    if contado == saldo_atual:
        raise AjusteSemEfeitoError(saldo_atual)
    if contado > saldo_atual:
        return MovementKind.ENTRADA, contado - saldo_atual
    return MovementKind.SAIDA, saldo_atual - contado
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_stock_adjustment.py -q`
Expected: PASS, 9 passed

- [ ] **Step 7: Commit**

```bash
git add src/stockflow/domain/enums/adjustment_reason.py \
        src/stockflow/domain/stock_adjustment.py \
        src/stockflow/domain/exceptions/adjustment_errors.py \
        tests/unit/test_stock_adjustment.py
git commit -m "feat(h11): add adjustment reason enum and counted-balance arithmetic"
```

---

### Task 2: Fonte declarativa do banco — colunas, CHECKs e a função

**Files:**
- Modify: `database/code/tables/05_movements.sql`
- Modify: `database/code/procedures/04a_movements.sql`
- Modify: `database/code/policies/01_security.sql:192`
- Modify (espelho): `database/supabase/schemas/tables/05_movements.sql`
- Modify (espelho): `database/supabase/schemas/procedures/04a_movements.sql`
- Modify (espelho): `database/supabase/schemas/policies/01_security.sql`
- Test: `tests/test_schema_declarativo.py`, `tests/unit/test_permission_matrix.py`

**Interfaces:**
- Consumes: `public.fn_has_role(uuid, public.user_role[])`,
  `public.fn_current_user_id()`, `public.products.stock integer NOT NULL
  CHECK (stock >= 0)`, trigger `trg_stock_movements_apply`.
- Produces: tipo `public.adjustment_reason`; colunas
  `stock_movements.adjustment_reason` e `stock_movements.counted_balance`;
  função `public.fn_register_adjustment(uuid, uuid, integer, integer,
  public.adjustment_reason, text) RETURNS uuid`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_schema_declarativo.py`:

```python
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


def test_h11_o_par_motivo_contagem_e_tudo_ou_nada():
    """Motivo sem contagem (ou o contrário) seria ajuste pela metade."""
    assert "ck_movements_adjustment_pair" in CODE_SQL


def test_h11_outro_sem_detalhe_e_recusado_pelo_banco():
    """A justificativa é regra do banco, não cortesia da tela.

    Sem este CHECK, quem chamasse a função por SQL gravaria `OUTRO` sem
    dizer nada — e o critério de aceite fala em justificativa, não em campo
    de formulário.
    """
    assert "ck_movements_adjustment_detail" in CODE_SQL


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


def test_h11_a_funcao_de_ajuste_esta_na_allowlist_de_execute():
    """Função fora da allowlist aplica no banco e quebra o app em runtime."""
    allowlist = (CODE / "policies" / "01_security.sql").read_text(encoding="utf-8")
    assert "'fn_register_adjustment'" in allowlist
```

Append to `tests/unit/test_permission_matrix.py`:

```python
def test_a_funcao_de_ajuste_exige_a_mesma_alcada_das_movimentacoes():
    """H11 reaproveita a área `movimentacoes`; o SQL tem que concordar.

    Sem este teste, alguém troca `fn_has_role(ADMIN, STOCK)` por
    `fn_is_member` dentro de `fn_register_adjustment` e nada fica vermelho:
    a matriz continua apontando para `fn_register_movement`, que não mudou.
    """
    do_sql = papeis_da_fonte("fn_register_adjustment")

    assert do_sql is not None, "fn_register_adjustment não existe em database/code/"
    assert do_sql == PERMISSION_MATRIX["movimentacoes"].gravar, (
        f"fn_register_adjustment exige {sorted(do_sql)}, mas a área "
        f"movimentacoes grava {sorted(PERMISSION_MATRIX['movimentacoes'].gravar)}"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_schema_declarativo.py -k h11 tests/unit/test_permission_matrix.py -k ajuste -q`
Expected: FAIL — `tipo public.adjustment_reason não declarado em database/code`

- [ ] **Step 3: Add the type, columns and constraints**

In `database/code/tables/05_movements.sql`, add the type right after the two
existing `CREATE TYPE`:

```sql
-- Motivo de um ajuste manual de inventário (H11). Lista fechada, e não texto
-- livre: "quanto sumiu por quebra neste mês" tem que ser consulta, e motivo
-- inválido tem que ser erro de tipo, não string que ninguém lê.
CREATE TYPE public.adjustment_reason AS ENUM
    ('CONTAGEM', 'QUEBRA', 'PERDA', 'VENCIMENTO', 'DEVOLUCAO', 'OUTRO');
```

Inside `CREATE TABLE public.stock_movements`, after `confirmed_on`:

```sql
    -- H11. NULL = movimentação comum; preenchido = ajuste manual. Marca, e
    -- não espécie nova: um `AJUSTE` de quantidade com sinal exigiria
    -- derrubar o `CHECK (quantity > 0)` acima e reescrever o `CASE` de
    -- fn_confirmed_balance.
    adjustment_reason public.adjustment_reason,
    -- O saldo que o operador AFIRMOU ter contado. Guardado, e não só
    -- validado na gravação, para que um relatório de reconciliação consiga
    -- reconferir a invariante depois em vez de confiar nela.
    counted_balance   integer,

    -- Constraint NOMEADA, e não um CHECK inline: a migration precisa criá-la
    -- com guarda sobre `pg_constraint`, e isso exige um nome. Deixar o
    -- Postgres gerar o nome aqui faria os dois lados declararem a mesma
    -- regra com identidades diferentes, e o `declarative sync` seguinte
    -- proporia mexer nela.
    CONSTRAINT ck_movements_counted_balance CHECK (
        counted_balance IS NULL OR counted_balance >= 0),

    -- Os dois andam juntos: motivo sem contagem é ajuste sem número, e
    -- contagem sem motivo é ajuste sem justificativa.
    CONSTRAINT ck_movements_adjustment_pair CHECK (
        (adjustment_reason IS NULL     AND counted_balance IS NULL)
     OR (adjustment_reason IS NOT NULL AND counted_balance IS NOT NULL)),

    -- A justificativa é regra do BANCO. Quem chamar a função por SQL direto
    -- também é recusado.
    CONSTRAINT ck_movements_adjustment_detail CHECK (
        adjustment_reason IS DISTINCT FROM 'OUTRO'
     OR btrim(coalesce(note, '')) <> '')
```

At the end of the same file, next to the other indexes:

```sql
-- Parcial, no molde de idx_stock_movements_supplier: o relatório de ajustes
-- percorre uma fração minúscula da tabela, e o índice cheio pagaria por
-- todas as movimentações comuns para servir essa fração.
CREATE INDEX idx_stock_movements_adjustment
    ON public.stock_movements (company_id, created_on)
    WHERE adjustment_reason IS NOT NULL;
```

- [ ] **Step 4: Add the function**

Append to `database/code/procedures/04a_movements.sql`:

```sql
-- Ajuste manual de inventário (H11).
--
-- O operador informa o saldo CONTADO e a função deriva o lançamento. Não é um
-- caminho paralelo ao saldo: grava uma movimentação comum já CONFIRMADA e
-- deixa o trigger de triggers/04 recalcular `products.stock`, como todo o
-- resto. Escrever o saldo aqui seria desfeito pela movimentação seguinte.
--
-- ATÔMICA de propósito, sem o par registrar/confirmar das irmãs: contagem é
-- uma afirmação sobre AGORA. Um ajuste pendente confirmado meia hora depois
-- aplicaria uma diferença calculada sobre um saldo que já mudou.
CREATE OR REPLACE FUNCTION public.fn_register_adjustment(
    p_company_id       uuid,
    p_product_id       uuid,
    p_counted_balance  integer,
    p_expected_balance integer,
    p_reason           public.adjustment_reason,
    p_detail           text DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_current integer;
    v_kind    public.movement_kind;
    v_qty     integer;
    v_detail  text := nullif(btrim(coalesce(p_detail, '')), '');
    v_id      uuid;
    v_final   integer;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para ajustar o estoque nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF p_counted_balance IS NULL OR p_counted_balance < 0 THEN
        RAISE EXCEPTION 'O saldo contado não pode ser negativo (recebido: %)',
            p_counted_balance USING ERRCODE = 'check_violation';
    END IF;

    IF p_reason IS NULL THEN
        RAISE EXCEPTION 'Informe o motivo do ajuste'
            USING ERRCODE = 'check_violation';
    END IF;

    IF p_reason = 'OUTRO' AND v_detail IS NULL THEN
        RAISE EXCEPTION 'O motivo "Outro" exige uma justificativa escrita'
            USING ERRCODE = 'check_violation';
    END IF;

    -- FOR UPDATE trava a linha do produto até o fim da transação: dois
    -- ajustes simultâneos do mesmo item serializam aqui, em vez de
    -- calcularem a diferença sobre o mesmo saldo e um sobrescrever o outro.
    SELECT stock INTO v_current
      FROM public.products
     WHERE id = p_product_id AND company_id = p_company_id AND active
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Produto não encontrado ou inativo nesta empresa'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- O saldo que a TELA exibiu faz parte do pedido. Recalcular em silêncio
    -- sobre um saldo que mudou daria um número que não é o contado nem o
    -- correto: se alguém confirmou uma entrada e pôs a mercadoria na
    -- prateleira, só uma recontagem resolve.
    IF p_expected_balance IS NOT NULL AND p_expected_balance <> v_current THEN
        RAISE EXCEPTION 'O saldo mudou desde a contagem (na tela: %, agora: %)',
            p_expected_balance, v_current USING ERRCODE = 'serialization_failure';
    END IF;

    IF p_counted_balance = v_current THEN
        RAISE EXCEPTION 'O saldo contado é igual ao saldo atual (%)', v_current
            USING ERRCODE = 'check_violation';
    END IF;

    IF p_counted_balance > v_current THEN
        v_kind := 'ENTRADA';
        v_qty  := p_counted_balance - v_current;
    ELSE
        v_kind := 'SAIDA';
        v_qty  := v_current - p_counted_balance;
    END IF;

    INSERT INTO public.stock_movements
           (company_id, product_id, kind, quantity, status, note,
            adjustment_reason, counted_balance, created_by, confirmed_on)
    VALUES (p_company_id, p_product_id, v_kind, v_qty, 'CONFIRMADA', v_detail,
            p_reason, p_counted_balance, public.fn_current_user_id(), now())
    RETURNING id INTO v_id;

    UPDATE public.products
       SET last_updated_by = public.fn_current_user_id()
     WHERE id = p_product_id;

    -- O trigger AFTER INSERT já recalculou products.stock quando o INSERT
    -- acima terminou. Reler e conferir é o que transforma "o saldo
    -- resultante" de expectativa em garantia: ou é o contado, ou a
    -- transação inteira volta atrás.
    SELECT stock INTO v_final FROM public.products WHERE id = p_product_id;
    IF v_final <> p_counted_balance THEN
        RAISE EXCEPTION 'Saldo resultante (%) diferente do contado (%); ajuste desfeito',
            v_final, p_counted_balance USING ERRCODE = 'check_violation';
    END IF;

    RETURN v_id;
END;
$$;
```

- [ ] **Step 5: Add the function to the EXECUTE allowlist**

In `database/code/policies/01_security.sql`, line ~192, extend the list:

```sql
    'fn_register_movement', 'fn_confirm_movement', 'fn_cancel_movement',
    'fn_register_adjustment',
```

- [ ] **Step 6: Mirror `code/` into `schemas/`**

Copy each edited file over its twin and prove the mirror is exact:

```bash
cp database/code/tables/05_movements.sql     database/supabase/schemas/tables/05_movements.sql
cp database/code/procedures/04a_movements.sql database/supabase/schemas/procedures/04a_movements.sql
cp database/code/policies/01_security.sql     database/supabase/schemas/policies/01_security.sql
diff -r database/code database/supabase/schemas && echo "espelho exato"
```

Expected: `espelho exato`

- [ ] **Step 7: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_schema_declarativo.py tests/unit/test_permission_matrix.py -q`
Expected: PASS — todo o arquivo, não só os testes novos: `test_schema_declarativo`
compara os dois lados e acusaria um espelho incompleto.

- [ ] **Step 8: Commit**

```bash
git add database/code database/supabase/schemas \
        tests/test_schema_declarativo.py tests/unit/test_permission_matrix.py
git commit -m "feat(h11): declare adjustment columns, constraints and fn_register_adjustment"
```

---

### Task 3: Migration idempotente

**Files:**
- Create: `database/supabase/migrations/<ts>_h11_manual_stock_adjustment.sql`
- Test: `tests/test_database_migrations.py`

**Interfaces:**
- Consumes: tudo o que a Task 2 declarou.
- Produces: nada para o código Python. É o artefato que o usuário aplica.

`<ts>` é `YYYYMMDDHHMMSS`, estritamente maior que `20261013140000` (a última
da cadeia). Obtenha com `date +%Y%m%d%H%M%S`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_database_migrations.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_database_migrations.py -k h11 -q`
Expected: FAIL com `migration h11_manual_stock_adjustment não encontrada`

- [ ] **Step 3: Write the migration**

```bash
TS=$(date +%Y%m%d%H%M%S)
echo "database/supabase/migrations/${TS}_h11_manual_stock_adjustment.sql"
```

Create that file:

```sql
-- H11: ajuste manual de inventário. Acrescenta a marca de ajuste às
-- movimentações e a função atômica que as grava.
--
-- Idempotente de ponta a ponta: o remoto já divergiu do repositório uma vez
-- (tinha `sales`/`sale_items` que a cadeia não descrevia), então esta
-- migration precisa aplicar tanto sobre um banco limpo quanto sobre um que
-- já tenha parte disto. Não recria tabela e não derruba nada: `stock_movements`
-- é o histórico de onde o saldo sai.
--
-- A transação é aberta AQUI: `supabase db push` manda cada comando
-- separadamente, em autocommit, e sem o BEGIN uma falha no meio deixaria as
-- colunas sem as constraints.

BEGIN;

DO $$
BEGIN
    IF to_regtype('public.adjustment_reason') IS NULL THEN
        CREATE TYPE public.adjustment_reason AS ENUM
            ('CONTAGEM', 'QUEBRA', 'PERDA', 'VENCIMENTO', 'DEVOLUCAO', 'OUTRO');
    END IF;
END;
$$;

ALTER TABLE public.stock_movements
    ADD COLUMN IF NOT EXISTS adjustment_reason public.adjustment_reason;
ALTER TABLE public.stock_movements
    ADD COLUMN IF NOT EXISTS counted_balance integer;

-- As constraints entram separadas das colunas porque `ADD COLUMN IF NOT
-- EXISTS` não aceita CHECK nomeado, e porque assim a aplicação sobre um
-- banco que já tinha as colunas (sem as regras) também as ganha.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_movements_counted_balance') THEN
        ALTER TABLE public.stock_movements
            ADD CONSTRAINT ck_movements_counted_balance
            CHECK (counted_balance IS NULL OR counted_balance >= 0);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_movements_adjustment_pair') THEN
        ALTER TABLE public.stock_movements
            ADD CONSTRAINT ck_movements_adjustment_pair CHECK (
                (adjustment_reason IS NULL     AND counted_balance IS NULL)
             OR (adjustment_reason IS NOT NULL AND counted_balance IS NOT NULL));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_movements_adjustment_detail') THEN
        ALTER TABLE public.stock_movements
            ADD CONSTRAINT ck_movements_adjustment_detail CHECK (
                adjustment_reason IS DISTINCT FROM 'OUTRO'
             OR btrim(coalesce(note, '')) <> '');
    END IF;
END;
$$;

-- DROP + CREATE seco em vez de `CREATE INDEX IF NOT EXISTS`: o regex de
-- tests/test_schema_declarativo.py já tolera a forma longa, mas a forma
-- curta é a que o resto da árvore usa.
DROP INDEX IF EXISTS public.idx_stock_movements_adjustment;
CREATE INDEX idx_stock_movements_adjustment
    ON public.stock_movements (company_id, created_on)
    WHERE adjustment_reason IS NOT NULL;

CREATE OR REPLACE FUNCTION public.fn_register_adjustment(
    p_company_id       uuid,
    p_product_id       uuid,
    p_counted_balance  integer,
    p_expected_balance integer,
    p_reason           public.adjustment_reason,
    p_detail           text DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_current integer;
    v_kind    public.movement_kind;
    v_qty     integer;
    v_detail  text := nullif(btrim(coalesce(p_detail, '')), '');
    v_id      uuid;
    v_final   integer;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para ajustar o estoque nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF p_counted_balance IS NULL OR p_counted_balance < 0 THEN
        RAISE EXCEPTION 'O saldo contado não pode ser negativo (recebido: %)',
            p_counted_balance USING ERRCODE = 'check_violation';
    END IF;

    IF p_reason IS NULL THEN
        RAISE EXCEPTION 'Informe o motivo do ajuste'
            USING ERRCODE = 'check_violation';
    END IF;

    IF p_reason = 'OUTRO' AND v_detail IS NULL THEN
        RAISE EXCEPTION 'O motivo "Outro" exige uma justificativa escrita'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT stock INTO v_current
      FROM public.products
     WHERE id = p_product_id AND company_id = p_company_id AND active
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Produto não encontrado ou inativo nesta empresa'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF p_expected_balance IS NOT NULL AND p_expected_balance <> v_current THEN
        RAISE EXCEPTION 'O saldo mudou desde a contagem (na tela: %, agora: %)',
            p_expected_balance, v_current USING ERRCODE = 'serialization_failure';
    END IF;

    IF p_counted_balance = v_current THEN
        RAISE EXCEPTION 'O saldo contado é igual ao saldo atual (%)', v_current
            USING ERRCODE = 'check_violation';
    END IF;

    IF p_counted_balance > v_current THEN
        v_kind := 'ENTRADA';
        v_qty  := p_counted_balance - v_current;
    ELSE
        v_kind := 'SAIDA';
        v_qty  := v_current - p_counted_balance;
    END IF;

    INSERT INTO public.stock_movements
           (company_id, product_id, kind, quantity, status, note,
            adjustment_reason, counted_balance, created_by, confirmed_on)
    VALUES (p_company_id, p_product_id, v_kind, v_qty, 'CONFIRMADA', v_detail,
            p_reason, p_counted_balance, public.fn_current_user_id(), now())
    RETURNING id INTO v_id;

    UPDATE public.products
       SET last_updated_by = public.fn_current_user_id()
     WHERE id = p_product_id;

    SELECT stock INTO v_final FROM public.products WHERE id = p_product_id;
    IF v_final <> p_counted_balance THEN
        RAISE EXCEPTION 'Saldo resultante (%) diferente do contado (%); ajuste desfeito',
            v_final, p_counted_balance USING ERRCODE = 'check_violation';
    END IF;

    RETURN v_id;
END;
$$;

REVOKE ALL ON FUNCTION public.fn_register_adjustment(
    uuid, uuid, integer, integer, public.adjustment_reason, text
) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.fn_register_adjustment(
    uuid, uuid, integer, integer, public.adjustment_reason, text
) TO app_backend, authenticated;

COMMIT;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_database_migrations.py tests/test_schema_declarativo.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add database/supabase/migrations tests/test_database_migrations.py
git commit -m "feat(h11): add idempotent migration for manual stock adjustment"
```

---

### Task 4: Tupla do histórico com comprimento fixo

Conserto de escopo, independente do resto. Sem ele o motivo do ajuste cai na
coluna Fornecedor sempre que o produto não tiver fornecedor — que é a maioria
das saídas.

**Files:**
- Modify: `src/stockflow/infrastructure/repositories/movement_mapper.py`
- Modify: `src/stockflow/infrastructure/repositories/demo_movement_repository.py:68-90`
- Modify: `src/stockflow/infrastructure/repositories/supabase_movement_repository.py:46`
- Modify: `src/stockflow/presentation/pages/movimentacoes.py:28-37`
- Test: `tests/unit/test_movement_repositories.py`

**Interfaces:**
- Produces: `row_to_movement(row, product_code="", product_name="",
  agora=None, supplier_name="", reason=None) -> tuple` com **10 posições
  sempre**: `(id, código, nome, espécie, quantidade, situação, observação,
  quando, fornecedor, motivo)`. Ausência é `VAZIO` (`"—"`).
  `rows_to_movements(rows, produtos=None, agora=None, fornecedores=None)`
  mantém a assinatura.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_movement_repositories.py`:

```python
# -------------------------------------------------------- tupla de 10 campos
# A cauda da tupla era OPCIONAL: o fornecedor só era acrescentado quando
# existia, e a tela lia `mov[8] if len(mov) > 8`. Pendurar o motivo do ajuste
# nisso colocaria "Quebra / avaria" na coluna Fornecedor toda vez que o
# produto não tivesse fornecedor — a maioria das saídas.

CAMPOS = 10
I_FORNECEDOR, I_MOTIVO = 8, 9


def test_movimentacao_sem_fornecedor_ainda_tem_dez_campos():
    repo = DemoMovementRepository(
        {"P1": Product("P1", "Arroz", "Grãos", "UN", "10,00", "5,00", True, "42", "Normal")},
        agora=AGORA,
    )
    repo.register(MovementInput("P1", MovementKind.SAIDA, 2, confirm=True))

    linha = repo.list_movements()[0]

    assert len(linha) == CAMPOS
    assert linha[I_FORNECEDOR] == VAZIO
    assert linha[I_MOTIVO] == VAZIO


def test_o_fornecedor_nao_escorrega_para_a_coluna_do_motivo():
    """Posição fixa: fornecedor é sempre 8, motivo é sempre 9."""
    tabelas = movimentos_falsos()
    repo = SupabaseMovementRepository(ClienteFalso(tabelas), COMPANY, agora=AGORA)

    for linha in repo.list_movements():
        assert len(linha) == CAMPOS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_movement_repositories.py -k "dez_campos or escorrega" -q`
Expected: FAIL com `assert 8 == 10`

- [ ] **Step 3: Make the mapper produce a fixed-width tuple**

In `src/stockflow/infrastructure/repositories/movement_mapper.py`, replace
`row_to_movement` and `rows_to_movements`:

```python
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
                    supplier_name="", reason=None) -> tuple:
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
        _rotulo_de_motivo(reason if reason is not None else row.get("adjustment_reason")),
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
```

Add the import at the top of the module, next to the other enum imports:

```python
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
```

- [ ] **Step 4: Make the demo adapter use it**

In `demo_movement_repository.py`, replace the body of `list_movements`:

```python
    def list_movements(self, product_code: str | None = None) -> tuple:
        """Da mais recente para a mais antiga, em todas as situações.

        Canceladas incluídas de propósito: escondê-las tiraria da tela a
        resposta para "por que o saldo subiu e voltou".
        """
        linhas = reversed(self._movements)
        if product_code:
            linhas = [m for m in linhas if m["product_code"] == product_code]
        result = []
        for linha in linhas:
            supplier_name = ""
            if linha.get("supplier_id"):
                supplier = (
                    self._suppliers.get(linha["supplier_id"])
                    if self._suppliers else None
                )
                supplier_name = getattr(supplier, "name", "") or "Fornecedor indisponível"
            result.append(row_to_movement(
                linha,
                product_code=linha["product_code"],
                product_name=self._nome_do_produto(linha["product_code"]),
                agora=self._agora,
                supplier_name=supplier_name,
            ))
        return tuple(result)
```

- [ ] **Step 5: Make the Supabase adapter read the new columns**

In `supabase_movement_repository.py`, extend `MOVEMENT_COLUMNS`:

```python
MOVEMENT_COLUMNS = (
    "id,product_id,supplier_id,kind,quantity,status,note,created_on,"
    "confirmed_on,adjustment_reason,counted_balance"
)
```

- [ ] **Step 6: Make the page read fixed indices**

In `src/stockflow/presentation/pages/movimentacoes.py`, replace the column
tuple and index constants:

```python
COLUMNS = ("Produto", "Espécie", "Quantidade", "Situação", "Observação",
           "Quando", "Fornecedor", "Motivo", "Ações")
ACTIONS_COLUMN = len(COLUMNS) - 1

# Índices da tupla que o repositório devolve. DEZ posições, sempre — ausência
# é travessão. Ver a nota em `movement_mapper.row_to_movement`.
(MOV_ID, MOV_CODE, MOV_NAME, MOV_KIND, MOV_QTY, MOV_STATUS, MOV_NOTE,
 MOV_WHEN, MOV_SUPPLIER, MOV_REASON) = range(10)
```

And in `set_movements`, replace the two trailing cells:

```python
            self.table.setItem(row, 6, QTableWidgetItem(str(mov[MOV_SUPPLIER])))
            motivo = QTableWidgetItem(str(mov[MOV_REASON]))
            self.table.setItem(row, 7, motivo)
```

- [ ] **Step 7: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q`
Expected: PASS. Se algum teste antigo falhar por ler `mov[8]` condicionalmente
ou por contar colunas, ajuste-o para os índices fixos — a mudança de contrato é
deliberada e está descrita no docstring de `row_to_movement`.

- [ ] **Step 8: Commit**

```bash
git add src/stockflow/infrastructure/repositories src/stockflow/presentation/pages/movimentacoes.py tests/
git commit -m "refactor(h11): give movement history rows a fixed ten-field shape"
```

---

### Task 5: DTO, porta e serviço

**Files:**
- Create: `src/stockflow/application/dto/adjustment_input.py`
- Modify: `src/stockflow/application/ports/movement_repository.py`
- Modify: `src/stockflow/application/services/movement_service.py`
- Test: `tests/unit/test_movement_service_adjust.py`

**Interfaces:**
- Consumes: `calcular_ajuste`, `AdjustmentReason`, `AjusteSemEfeitoError`,
  `SaldoDesatualizadoError` (Task 1); `ensure_can_move_stock` (já existe).
- Produces:
  - `AdjustmentInput(product_code: str, counted_balance: int,
    expected_balance: int, reason: AdjustmentReason, detail: str = "")`
  - `MovementRepository.adjust(data: AdjustmentInput) -> str`
  - `MovementService.adjust(session, data: AdjustmentInput) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_movement_service_adjust.py`:

```python
"""O serviço de ajuste recusa antes de tocar no repositório (H11).

A ordem importa e é a mesma do `ProductService`: permissão primeiro, inclusive
antes de leitura. Um papel sem alçada não pode nem descobrir, pela mensagem de
erro, se o produto existe.
"""

import pytest

from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.application.services.movement_service import MovementService
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.presentation.demo_products import Product


class RepositorioEspiao:
    """Registra o que foi chamado. Qualquer chamada é falha num teste de recusa."""

    def __init__(self):
        self.chamadas = []

    def adjust(self, data):
        self.chamadas.append(data)
        return "MOV-001"


class CatalogoFalso:
    def __init__(self, produtos):
        self._produtos = produtos

    def get(self, code):
        return self._produtos.get(code)


class SessaoFalsa:
    def __init__(self, role):
        self.role = role


def produto(code="P1", active=True, stock="42"):
    return Product(code, "Arroz", "Grãos", "UN", "10,00", "5,00", active, stock, "Normal")


def servico(produtos=None):
    repo = RepositorioEspiao()
    catalogo = CatalogoFalso(produtos if produtos is not None else {"P1": produto()})
    return MovementService(repo, product_repository=catalogo), repo


def pedido(**kwargs):
    base = dict(
        product_code="P1", counted_balance=38, expected_balance=42,
        reason=AdjustmentReason.QUEBRA, detail="",
    )
    base.update(kwargs)
    return AdjustmentInput(**base)


def test_vendedor_e_recusado_sem_tocar_no_repositorio():
    service, repo = servico()

    with pytest.raises(PermissionDeniedError):
        service.adjust(SessaoFalsa(UserRole.SELLER), pedido())

    assert repo.chamadas == [], "o repositório foi chamado apesar da recusa"


def test_sessao_ausente_e_recusada():
    service, repo = servico()

    with pytest.raises(PermissionDeniedError):
        service.adjust(None, pedido())

    assert repo.chamadas == []


@pytest.mark.parametrize("papel", [UserRole.ADMIN, UserRole.STOCK])
def test_admin_e_estoquista_ajustam(papel):
    service, repo = servico()

    assert service.adjust(SessaoFalsa(papel), pedido()) == "MOV-001"
    assert len(repo.chamadas) == 1


def test_motivo_outro_sem_detalhe_e_recusado_antes_da_rede():
    service, repo = servico()

    with pytest.raises(ValueError, match="Outro"):
        service.adjust(
            SessaoFalsa(UserRole.STOCK),
            pedido(reason=AdjustmentReason.OUTRO, detail="   "),
        )

    assert repo.chamadas == []


def test_motivo_outro_com_detalhe_passa():
    service, repo = servico()

    service.adjust(
        SessaoFalsa(UserRole.STOCK),
        pedido(reason=AdjustmentReason.OUTRO, detail="Caixa amassada na doca"),
    )

    assert len(repo.chamadas) == 1


def test_produto_inativo_e_recusado():
    service, repo = servico({"P1": produto(active=False)})

    with pytest.raises(ValueError, match="ativo"):
        service.adjust(SessaoFalsa(UserRole.STOCK), pedido())

    assert repo.chamadas == []


def test_contado_negativo_e_recusado():
    service, repo = servico()

    with pytest.raises(ValueError):
        service.adjust(SessaoFalsa(UserRole.STOCK), pedido(counted_balance=-1))

    assert repo.chamadas == []


def test_sem_diferenca_nao_vira_requisicao():
    """Contado igual ao exibido: a recusa é local, não um erro do Postgres."""
    service, repo = servico()

    with pytest.raises(ValueError):
        service.adjust(
            SessaoFalsa(UserRole.STOCK),
            pedido(counted_balance=42, expected_balance=42),
        )

    assert repo.chamadas == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_movement_service_adjust.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'stockflow.application.dto.adjustment_input'`

- [ ] **Step 3: Write the DTO**

Create `src/stockflow/application/dto/adjustment_input.py`:

```python
"""Dados de um ajuste manual como a tela os entrega (H11)."""

from dataclasses import dataclass

from stockflow.domain.enums.adjustment_reason import AdjustmentReason


@dataclass(frozen=True)
class AdjustmentInput:
    """Campos de `fn_register_adjustment`, menos a identidade.

    `created_by` NÃO entra aqui, pela mesma razão de `MovementInput`: quem
    ajusta é a sessão, e o banco a resolve por `fn_current_user_id()`.
    Aceitar um identificador vindo da tela permitiria registrar o ajuste em
    nome de outra pessoa — e ajuste manual é justamente a operação que
    precisa de autor confiável.

    `expected_balance` é o saldo que a TELA exibiu, não um palpite: a função
    recusa quando ele não bate com o saldo real, porque entre a contagem e o
    clique alguém pode ter movimentado o mesmo produto.
    """

    product_code: str
    counted_balance: int
    expected_balance: int
    reason: AdjustmentReason
    detail: str = ""
```

- [ ] **Step 4: Extend the port**

Append to the `MovementRepository` protocol in
`src/stockflow/application/ports/movement_repository.py`:

```python
    def adjust(self, data: AdjustmentInput) -> str:
        """Ajuste manual de inventário: uma operação, indivisível.

        Não tem par registrar/confirmar como as outras de propósito. Uma
        contagem é uma afirmação sobre AGORA; um ajuste pendente confirmado
        depois aplicaria uma diferença calculada sobre um saldo que já mudou,
        e o saldo final não seria o contado.
        """
        ...
```

With the import at the top:

```python
from stockflow.application.dto.adjustment_input import AdjustmentInput
```

- [ ] **Step 5: Write the service method**

Append to `MovementService` in
`src/stockflow/application/services/movement_service.py`:

```python
    def adjust(self, session, data: AdjustmentInput) -> str:
        """Ajusta o saldo para o valor contado. Levanta `ValueError` em dado inválido.

        Permissão primeiro, como em `register`: a mesma alçada ADMIN/STOCK,
        porque `fn_register_adjustment` checa o mesmo `fn_has_role`. As
        validações abaixo não substituem as do banco — elas dão a mensagem
        certa em português sem gastar requisição, e o banco segue sendo quem
        de fato impede a gravação.
        """
        ensure_can_move_stock(session, action="ajustar o estoque")

        if not (data.product_code or "").strip():
            raise ValueError("Selecione o produto do ajuste.")

        if self._product_repository is not None:
            product = self._product_repository.get(data.product_code)
            if product is None or not product.active:
                raise ValueError("Selecione um produto ativo.")

        motivo = AdjustmentReason.from_value(data.reason)
        if motivo.exige_detalhe and not str(data.detail or "").strip():
            raise ValueError('O motivo "Outro" exige uma justificativa escrita.')

        # `calcular_ajuste` levanta em contado negativo e em diferença zero.
        # Chamá-la aqui é o que faz a tela receber a recusa nomeada em vez de
        # uma mensagem do Postgres traduzida pela metade.
        calcular_ajuste(_para_inteiro(data.expected_balance),
                        _para_inteiro(data.counted_balance))

        return self._repository.adjust(data)
```

With the imports at the top of the module:

```python
from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.stock_adjustment import calcular_ajuste
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_movement_service_adjust.py -q`
Expected: PASS, 10 passed

- [ ] **Step 7: Commit**

```bash
git add src/stockflow/application tests/unit/test_movement_service_adjust.py
git commit -m "feat(h11): add adjustment DTO, repository port method and service guard"
```

---

### Task 6: Adaptador de demonstração

**Files:**
- Modify: `src/stockflow/infrastructure/repositories/demo_movement_repository.py`
- Test: `tests/unit/test_movement_repositories.py`

**Interfaces:**
- Consumes: `AdjustmentInput`, `calcular_ajuste`, `AdjustmentReason`,
  `SaldoDesatualizadoError`.
- Produces: `DemoMovementRepository.adjust(data: AdjustmentInput) -> str`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_movement_repositories.py`:

```python
# ------------------------------------------------------------- ajuste (H11)
# Do adaptador de demonstração o que se prova é mais forte que do de banco,
# porque ele É a implementação: aqui não há trigger nem transação, então a
# atomicidade e o saldo resultante precisam ser código testado.

from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.exceptions.adjustment_errors import SaldoDesatualizadoError


def catalogo_de_um(stock="42", active=True):
    return {"P1": Product("P1", "Arroz", "Grãos", "UN", "10,00", "5,00",
                          active, stock, "Normal")}


def ajuste(**kwargs):
    base = dict(product_code="P1", counted_balance=38, expected_balance=42,
                reason=AdjustmentReason.QUEBRA, detail="")
    base.update(kwargs)
    return AdjustmentInput(**base)


def test_ajuste_leva_o_saldo_exatamente_ao_contado():
    produtos = catalogo_de_um("42")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.adjust(ajuste(counted_balance=38))

    assert produtos["P1"].stock == "38"


def test_contar_mais_do_que_havia_vira_entrada():
    produtos = catalogo_de_um("42")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.adjust(ajuste(counted_balance=50, reason=AdjustmentReason.CONTAGEM))

    assert produtos["P1"].stock == "50"
    assert repo.list_movements()[0][3] == MovementKind.ENTRADA.label


def test_o_ajuste_nasce_confirmado_e_carrega_o_motivo():
    """Não há par registrar/confirmar: a contagem vale no ato."""
    produtos = catalogo_de_um("42")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.adjust(ajuste(counted_balance=38))
    linha = repo.list_movements()[0]

    assert linha[5] == MovementStatus.CONFIRMADA.label
    assert linha[9] == AdjustmentReason.QUEBRA.label


def test_saldo_mudou_desde_a_contagem_e_recusado_sem_gravar():
    produtos = catalogo_de_um("45")   # alguém movimentou; a tela viu 42
    repo = DemoMovementRepository(produtos, agora=AGORA)

    with pytest.raises(SaldoDesatualizadoError):
        repo.adjust(ajuste(expected_balance=42, counted_balance=38))

    assert produtos["P1"].stock == "45", "o saldo foi alterado apesar da recusa"
    assert repo.list_movements() == ()


def test_produto_inativo_nao_e_ajustado():
    produtos = catalogo_de_um("42", active=False)
    repo = DemoMovementRepository(produtos, agora=AGORA)

    with pytest.raises(ValueError):
        repo.adjust(ajuste())

    assert repo.list_movements() == ()


def test_outro_sem_detalhe_e_recusado_como_no_banco():
    """Espelha `ck_movements_adjustment_detail`.

    Sem isto, o modo demonstração aceitaria o que o Postgres recusa, e o bug
    só apareceria para quem roda com banco.
    """
    produtos = catalogo_de_um("42")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    with pytest.raises(ValueError):
        repo.adjust(ajuste(reason=AdjustmentReason.OUTRO, detail=""))

    assert repo.list_movements() == ()


def test_zerar_o_saldo_e_ajuste_valido():
    produtos = catalogo_de_um("5")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.adjust(ajuste(counted_balance=0, expected_balance=5,
                       reason=AdjustmentReason.PERDA))

    assert produtos["P1"].stock == "0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_movement_repositories.py -k ajuste -q`
Expected: FAIL com `AttributeError: 'DemoMovementRepository' object has no attribute 'adjust'`

- [ ] **Step 3: Implement `adjust`**

Append to `DemoMovementRepository`, after `cancel`:

```python
    def adjust(self, data) -> str:
        """Ajuste manual de inventário, imitando `fn_register_adjustment`.

        A ordem das recusas é a MESMA da função SQL, e isso não é capricho:
        o modo demonstração que aceitasse o que o Postgres recusa esconderia
        o bug de quem não roda com banco até a primeira gravação real.

        O saldo resultante é conferido ANTES de mexer no catálogo. Lá a
        garantia vem da transação; aqui não há transação, então a única
        forma de não deixar estado pela metade é calcular, conferir e só
        então aplicar.
        """
        produto = self._products.get(data.product_code)
        if produto is None:
            raise LookupError(f"Produto {data.product_code} não encontrado.")
        if not produto.active:
            raise ValueError("Selecione um produto ativo.")

        motivo = AdjustmentReason.from_value(data.reason)
        detalhe = str(data.detail or "").strip()
        if motivo.exige_detalhe and not detalhe:
            raise ValueError('O motivo "Outro" exige uma justificativa escrita.')

        atual = to_int(produto.stock)
        esperado = data.expected_balance
        if esperado is not None and to_int(esperado) != atual:
            raise SaldoDesatualizadoError.de_saldos(to_int(esperado), atual)

        contado = to_int(data.counted_balance)
        especie, quantidade = calcular_ajuste(atual, contado)

        # A conferência do saldo resultante, antes de qualquer escrita. Se
        # `calcular_ajuste` e `_aplicar_no_saldo` algum dia discordarem, é
        # aqui que aparece — e nada foi alterado ainda.
        if atual + especie.sinal * quantidade != contado:
            raise AssertionError(
                f"Ajuste calculado levaria o saldo a "
                f"{atual + especie.sinal * quantidade}, não ao contado {contado}."
            )

        agora = self._agora or datetime.now()
        linha = {
            "id": self._proximo_id(),
            "product_code": data.product_code,
            "kind": especie.value,
            "quantity": quantidade,
            "status": MovementStatus.CONFIRMADA.value,
            "note": detalhe,
            "supplier_id": None,
            "adjustment_reason": motivo.value,
            "counted_balance": contado,
            "created_on": agora,
            "confirmed_on": agora,
        }
        self._aplicar_no_saldo(linha, sentido=1)
        self._movements.append(linha)
        return linha["id"]
```

With the imports at the top of the module:

```python
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.exceptions.adjustment_errors import SaldoDesatualizadoError
from stockflow.domain.stock_adjustment import calcular_ajuste
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_movement_repositories.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stockflow/infrastructure/repositories/demo_movement_repository.py tests/unit/test_movement_repositories.py
git commit -m "feat(h11): implement manual adjustment in the demo movement adapter"
```

---

### Task 7: Adaptador Supabase

**Files:**
- Modify: `src/stockflow/infrastructure/repositories/movement_mapper.py`
- Modify: `src/stockflow/infrastructure/repositories/supabase_movement_repository.py`
- Test: `tests/unit/test_movement_repositories.py`

**Interfaces:**
- Produces:
  - `adjustment_input_to_args(data, company_id, product_id) -> dict` com as
    chaves `p_company_id`, `p_product_id`, `p_counted_balance`,
    `p_expected_balance`, `p_reason`, `p_detail`.
  - `SupabaseMovementRepository.adjust(data: AdjustmentInput) -> str`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_movement_repositories.py`:

```python
def test_ajuste_chama_a_rpc_com_o_uuid_e_o_motivo_cru():
    """A tela trabalha com código; a função exige uuid e o valor do enum."""
    tabelas = movimentos_falsos()
    cliente = ClienteFalso(tabelas)
    repo = SupabaseMovementRepository(cliente, COMPANY, agora=AGORA)
    repo.list_movements()   # alimenta o cache barcode -> uuid

    repo.adjust(ajuste(product_code="PRD-009", counted_balance=38,
                       expected_balance=18, reason=AdjustmentReason.QUEBRA,
                       detail=" caixa amassada "))

    nome, args = cliente.chamadas_rpc[-1]
    assert nome == "fn_register_adjustment"
    assert args["p_product_id"] == PRODUTO_ID
    assert args["p_counted_balance"] == 38
    assert args["p_expected_balance"] == 18
    assert args["p_reason"] == "QUEBRA"
    assert args["p_detail"] == "caixa amassada", "o detalhe precisa chegar aparado"


def test_detalhe_vazio_vira_nulo_e_nao_string_vazia():
    """A coluna é nullable e "não escrevi" é ausência.

    Gravar `''` faria um relatório que filtra por detalhe preenchido
    encontrar ajustes sem detalhe nenhum.
    """
    tabelas = movimentos_falsos()
    cliente = ClienteFalso(tabelas)
    repo = SupabaseMovementRepository(cliente, COMPANY, agora=AGORA)
    repo.list_movements()

    repo.adjust(ajuste(product_code="PRD-009", detail="   "))

    assert cliente.chamadas_rpc[-1][1]["p_detail"] is None


def test_recusa_de_permissao_na_rpc_de_ajuste_vira_erro_de_dominio():
    """42501 tem que cair nos `except PermissionDeniedError` já instalados.

    Sem a tradução, a recusa sobe como exceção crua do cliente HTTP e
    aparece um traceback onde deveria aparecer a mensagem de permissão.
    """
    tabelas = movimentos_falsos()
    cliente = ClienteFalso(tabelas, rpc_erros={
        "fn_register_adjustment": ErroDoPostgrest("permission denied", "42501"),
    })
    repo = SupabaseMovementRepository(cliente, COMPANY, role="SELLER", agora=AGORA)
    repo._ids["PRD-009"] = PRODUTO_ID

    with pytest.raises(PermissionDeniedError, match="ajustar o estoque"):
        repo.adjust(ajuste(product_code="PRD-009"))


def test_saldo_desatualizado_no_banco_vira_erro_nomeado():
    """40001 não é falha de sistema: é pedido de recontagem.

    Sem o nome próprio, a tela mostraria "serialization_failure" para quem
    só precisa contar de novo.
    """
    tabelas = movimentos_falsos()
    cliente = ClienteFalso(tabelas, rpc_erros={
        "fn_register_adjustment": ErroDoPostgrest(
            "O saldo mudou desde a contagem (na tela: 42, agora: 45)", "40001"),
    })
    repo = SupabaseMovementRepository(cliente, COMPANY, agora=AGORA)
    repo._ids["PRD-009"] = PRODUTO_ID

    with pytest.raises(SaldoDesatualizadoError, match="45"):
        repo.adjust(ajuste(product_code="PRD-009"))
```

O cliente falso compartilhado já tem tudo o que estes testes usam, com esta
API exata — confira antes de inventar outra:

```python
ClienteFalso(tabelas=None, rpc_resultados=None, rpc_erros=None)
#   .chamadas_rpc -> lista de (nome, args)
#   rpc_erros     -> {nome_da_funcao: excecao}
ErroDoPostgrest(message, code=None)   # mensagem PRIMEIRO, código depois
```

O produto do catálogo falso é `PRD-009` (uuid em `PRODUTO_ID`, saldo 18).
Reusar o falso em vez de escrever outro não é economia: duas imitações do
cliente divergem, e a que o teste novo escrevesse poderia aceitar um
encadeamento que o cliente real recusa.

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_movement_repositories.py -k "rpc_com_o_uuid or detalhe_vazio or recusa_de_permissao_na_rpc or saldo_desatualizado_no_banco" -q`
Expected: FAIL com `AttributeError: 'SupabaseMovementRepository' object has no attribute 'adjust'`

- [ ] **Step 3: Add the args builder**

Append to `src/stockflow/infrastructure/repositories/movement_mapper.py`:

```python
def adjustment_input_to_args(data, company_id, product_id) -> dict:
    """Argumentos nomeados de `fn_register_adjustment`.

    `p_expected_balance` vai junto e NÃO é opcional: é o saldo que a tela
    exibiu, e é ele que faz a função recusar quando outra pessoa movimentou o
    produto no meio. Omiti-lo transformaria "esqueci de passar" em "não quero
    a checagem de concorrência".

    Detalhe vazio vira NULL, não string vazia, pelo mesmo motivo da nota em
    `movement_input_to_register_args`.
    """
    detalhe = str(getattr(data, "detail", "") or "").strip()
    return {
        "p_company_id": company_id,
        "p_product_id": product_id,
        "p_counted_balance": to_int(data.counted_balance),
        "p_expected_balance": to_int(data.expected_balance),
        "p_reason": AdjustmentReason.from_value(data.reason).value,
        "p_detail": detalhe or None,
    }
```

- [ ] **Step 4: Implement `adjust` and the 40001 translation**

In `supabase_movement_repository.py`, register the action label:

```python
ACTION_BY_RPC = {
    "fn_register_movement": "registrar movimentações",
    "fn_register_supplier_movement": "registrar compras",
    "fn_confirm_movement": "confirmar movimentações",
    "fn_cancel_movement": "cancelar movimentações",
    "fn_register_adjustment": "ajustar o estoque",
}

# SQLSTATE que `fn_register_adjustment` usa para "o saldo mudou desde a
# contagem". Não é falha de sistema nem erro do usuário: é pedido de
# recontagem, e precisa de um tipo próprio para a tela poder dizer isso.
STALE_BALANCE_SQLSTATE = "40001"
```

Add the method after `cancel`:

```python
    def adjust(self, data) -> str:
        """Ajuste manual: uma rpc, uma transação, saldo conferido lá dentro.

        Sem par registrar/confirmar, ao contrário das irmãs. A conferência do
        saldo resultante acontece DENTRO da função, onde ela é atômica;
        refazê-la aqui depois da resposta compararia contra uma leitura nova,
        que outra pessoa já pode ter mudado.
        """
        product_id = self._product_id(data.product_code)
        if product_id is None:
            raise LookupError(f"Produto {data.product_code} não encontrado.")
        args = adjustment_input_to_args(data, self._company_id, product_id)
        return self._rpc("fn_register_adjustment", args)
```

Extend `_rpc` to translate the stale-balance refusal:

```python
    def _rpc(self, name: str, args: dict):
        """Chama a função e traduz as recusas conhecidas para erros de domínio.

        Sem esta tradução, uma recusa chegaria à tela como exceção crua do
        cliente HTTP e cairia fora dos `except` que a aplicação instalou —
        apareceria um traceback onde deveria aparecer a mensagem.
        """
        try:
            response = self._client.rpc(name, args).execute()
        except Exception as erro:
            if _e_recusa_de_permissao(erro):
                raise PermissionDeniedError(
                    ACTION_BY_RPC.get(name, f"executar {name}"), self._role
                ) from erro
            if str(getattr(erro, "code", "")) == STALE_BALANCE_SQLSTATE:
                # A mensagem do servidor já traz os dois saldos; reescrevê-la
                # aqui criaria uma segunda redação da mesma recusa.
                raise SaldoDesatualizadoError(
                    f"{_mensagem(erro)}. Reconte o produto antes de ajustar."
                ) from erro
            raise
        return getattr(response, "data", None)
```

With the imports at the top of the module:

```python
from stockflow.domain.exceptions.adjustment_errors import SaldoDesatualizadoError
from stockflow.infrastructure.repositories.movement_mapper import (
    adjustment_input_to_args,
    movement_input_to_register_args,
    rows_to_movements,
)
from stockflow.infrastructure.repositories.supabase_product_repository import (
    _e_recusa_de_permissao,
    _mensagem,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/stockflow/infrastructure/repositories tests/unit
git commit -m "feat(h11): call fn_register_adjustment from the supabase adapter"
```

---

### Task 8: Card de ajuste na tela de Movimentações

**Files:**
- Modify: `src/stockflow/presentation/pages/movimentacoes.py`
- Test: `tests/test_movimentacoes_na_tela.py`

**Interfaces:**
- Consumes: `calcular_ajuste`, `AdjustmentReason`, `AjusteSemEfeitoError`,
  `AdjustmentInput`, `selectable_products` (já usado na página).
- Produces, em `MovimentacoesPage`:
  - sinal `adjust_requested = Signal(object)` carregando `AdjustmentInput`
  - `ajuste_produto_combo`, `ajuste_contado_input`, `ajuste_motivo_combo`,
    `ajuste_detalhe_input`, `ajuste_aplicar_button`, `ajuste_previa_label`,
    `ajuste_saldo_label`
  - `limpar_ajuste()`, `mostrar_recusa_de_ajuste(mensagem)`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_movimentacoes_na_tela.py`:

```python
# ------------------------------------------------------------- ajuste (H11)

from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.domain.enums.adjustment_reason import AdjustmentReason


def catalogo_para_ajuste():
    from stockflow.presentation.demo_products import Product

    return {"P1": Product("P1", "Arroz", "Grãos", "UN", "10,00", "5,00",
                          True, "42", "Normal")}


def selecionar_produto_de_ajuste(page, code="P1"):
    page.ajuste_produto_combo.setCurrentIndex(
        page.ajuste_produto_combo.findData(code)
    )


def test_a_tela_mostra_o_saldo_atual_do_produto_escolhido(qapp):
    page = MovimentacoesPage(catalogo_para_ajuste())

    selecionar_produto_de_ajuste(page)

    assert "42" in page.ajuste_saldo_label.text()


def test_a_previa_diz_a_especie_e_a_quantidade_antes_do_clique(qapp):
    page = MovimentacoesPage(catalogo_para_ajuste())
    selecionar_produto_de_ajuste(page)

    page.ajuste_contado_input.setValue(38)

    texto = page.ajuste_previa_label.text().upper()
    assert "SAÍDA" in texto or "SAIDA" in texto
    assert "4" in texto


def test_contar_mais_mostra_entrada(qapp):
    page = MovimentacoesPage(catalogo_para_ajuste())
    selecionar_produto_de_ajuste(page)

    page.ajuste_contado_input.setValue(50)

    assert "ENTRADA" in page.ajuste_previa_label.text().upper()
    assert "8" in page.ajuste_previa_label.text()


def test_sem_diferenca_desabilita_o_botao(qapp):
    """A recusa chega antes do clique, não como erro vindo do banco."""
    page = MovimentacoesPage(catalogo_para_ajuste())
    selecionar_produto_de_ajuste(page)

    page.ajuste_contado_input.setValue(42)

    assert not page.ajuste_aplicar_button.isEnabled()
    assert "sem diferença" in page.ajuste_previa_label.text().casefold()


def test_outro_sem_detalhe_nao_emite_o_pedido(qapp):
    page = MovimentacoesPage(catalogo_para_ajuste())
    pedidos = []
    page.adjust_requested.connect(pedidos.append)
    selecionar_produto_de_ajuste(page)
    page.ajuste_contado_input.setValue(38)
    page.ajuste_motivo_combo.setCurrentIndex(
        page.ajuste_motivo_combo.findData(AdjustmentReason.OUTRO)
    )

    page.ajuste_aplicar_button.click()

    assert pedidos == []
    assert "justificativa" in page.warning_label.text().casefold()


def test_aplicar_emite_o_pedido_com_o_saldo_que_a_tela_exibiu(qapp):
    page = MovimentacoesPage(catalogo_para_ajuste())
    pedidos = []
    page.adjust_requested.connect(pedidos.append)
    selecionar_produto_de_ajuste(page)
    page.ajuste_contado_input.setValue(38)
    page.ajuste_motivo_combo.setCurrentIndex(
        page.ajuste_motivo_combo.findData(AdjustmentReason.QUEBRA)
    )

    page.ajuste_aplicar_button.click()

    assert len(pedidos) == 1
    pedido = pedidos[0]
    assert isinstance(pedido, AdjustmentInput)
    assert (pedido.product_code, pedido.counted_balance) == ("P1", 38)
    assert pedido.expected_balance == 42, (
        "sem o saldo exibido a função não tem como detectar que ele mudou"
    )
    assert pedido.reason is AdjustmentReason.QUEBRA


def test_papel_sem_alcada_nao_opera_o_card(qapp):
    page = MovimentacoesPage(catalogo_para_ajuste())

    page.apply_permission(False)

    assert not page.ajuste_aplicar_button.isEnabled()
    assert not page.ajuste_contado_input.isEnabled()
    assert not page.ajuste_motivo_combo.isEnabled()


def test_produto_inativo_sai_da_oferta_do_ajuste(qapp):
    import dataclasses

    produtos = catalogo_para_ajuste()
    page = MovimentacoesPage(produtos)
    produtos["P1"] = dataclasses.replace(produtos["P1"], active=False)

    page.reload_products(produtos)

    assert page.ajuste_produto_combo.findData("P1") < 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_movimentacoes_na_tela.py -k ajuste -q`
Expected: FAIL com `AttributeError: 'MovimentacoesPage' object has no attribute 'ajuste_produto_combo'`

- [ ] **Step 3: Add the signal and build the card**

In `src/stockflow/presentation/pages/movimentacoes.py`, add the signal next
to the existing three:

```python
    adjust_requested = Signal(object)       # AdjustmentInput
```

Add the card to the layout, between the form and the table:

```python
        layout.addWidget(self._create_form())
        layout.addWidget(self._create_adjustment_form())
        layout.addWidget(self._create_table(), 1)
```

Add the builder method:

```python
    def _create_adjustment_form(self):
        """Ajuste manual de inventário (H11).

        Card separado do de entrada/saída porque a pergunta é outra: lá se
        informa o que ENTROU ou SAIU, aqui se informa o que EXISTE. Misturar
        os dois num formulário só faria o campo de quantidade significar
        coisas diferentes conforme o modo.
        """
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(inventory.TABLE_CARD_QSS)
        fora = QVBoxLayout(card)
        fora.setContentsMargins(18, 16, 18, 16)
        fora.setSpacing(10)

        titulo = QLabel("Ajuste manual de inventário")
        titulo.setStyleSheet(inventory.SUBTITLE_QSS)
        fora.addWidget(titulo)

        linha = QHBoxLayout()
        linha.setSpacing(10)

        self.ajuste_produto_combo = QComboBox()
        self.ajuste_produto_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.ajuste_produto_combo.setMinimumContentsLength(12)
        self.ajuste_produto_combo.setFixedHeight(42)
        self.ajuste_produto_combo.setAccessibleName("Produto do ajuste")
        self.ajuste_produto_combo.currentIndexChanged.connect(self._atualizar_previa)

        self.ajuste_saldo_label = QLabel("Saldo atual: —")
        self.ajuste_saldo_label.setAccessibleName("Saldo atual do produto")

        self.ajuste_contado_input = QSpinBox()
        self.ajuste_contado_input.setRange(0, 999999)
        self.ajuste_contado_input.setFixedHeight(42)
        self.ajuste_contado_input.setAccessibleName("Saldo contado")
        self.ajuste_contado_input.valueChanged.connect(self._atualizar_previa)

        self.ajuste_previa_label = QLabel("")
        self.ajuste_previa_label.setAccessibleName("Prévia do ajuste")

        linha.addWidget(self.ajuste_produto_combo, 3)
        linha.addWidget(self.ajuste_saldo_label, 1)
        linha.addWidget(self.ajuste_contado_input, 1)
        linha.addWidget(self.ajuste_previa_label, 2)
        fora.addLayout(linha)

        acoes = QHBoxLayout()
        acoes.setSpacing(10)

        self.ajuste_motivo_combo = QComboBox()
        self.ajuste_motivo_combo.setFixedHeight(42)
        self.ajuste_motivo_combo.setAccessibleName("Motivo do ajuste")
        for motivo in AdjustmentReason:
            self.ajuste_motivo_combo.addItem(motivo.label, motivo)
        self.ajuste_motivo_combo.currentIndexChanged.connect(self._atualizar_detalhe)

        self.ajuste_detalhe_input = QLineEdit()
        self.ajuste_detalhe_input.setFixedHeight(42)

        self.ajuste_aplicar_button = QPushButton(" Aplicar ajuste")
        self.ajuste_aplicar_button.setFixedHeight(42)
        self.ajuste_aplicar_button.setStyleSheet(inventory.NEW_BUTTON_QSS)
        self.ajuste_aplicar_button.setIcon(qta.icon("fa5s.balance-scale", color="white"))
        self.ajuste_aplicar_button.setIconSize(QSize(13, 13))
        self.ajuste_aplicar_button.clicked.connect(self._aplicar_ajuste)

        acoes.addWidget(self.ajuste_motivo_combo, 1)
        acoes.addWidget(self.ajuste_detalhe_input, 2)
        acoes.addWidget(self.ajuste_aplicar_button)
        fora.addLayout(acoes)

        self._atualizar_detalhe()
        return card
```

- [ ] **Step 4: Add the live preview and the submit handler**

```python
    def _saldo_do_produto_de_ajuste(self):
        """Saldo atual do produto escolhido, ou `None` se nenhum."""
        codigo = self.ajuste_produto_combo.currentData()
        produto = self.products.get(codigo) if codigo else None
        return None if produto is None else to_int(produto.stock)

    def _atualizar_previa(self, *_):
        """Mostra o lançamento que o ajuste vai gerar, antes do clique.

        Usa `calcular_ajuste`, a mesma função que o serviço chama: uma
        segunda conta aqui é como a tela de Estoque divergiu de
        `fn_stock_state` antes da US03.
        """
        atual = self._saldo_do_produto_de_ajuste()
        if atual is None:
            self.ajuste_saldo_label.setText("Saldo atual: —")
            self.ajuste_previa_label.setText("")
            self.ajuste_aplicar_button.setEnabled(False)
            return

        self.ajuste_saldo_label.setText(f"Saldo atual: {atual}")
        try:
            especie, quantidade = calcular_ajuste(
                atual, self.ajuste_contado_input.value()
            )
        except AjusteSemEfeitoError:
            self.ajuste_previa_label.setText("Sem diferença — nada a ajustar")
            self.ajuste_aplicar_button.setEnabled(False)
            return
        except ValueError as erro:
            self.ajuste_previa_label.setText(str(erro))
            self.ajuste_aplicar_button.setEnabled(False)
            return

        self.ajuste_previa_label.setText(
            f"→ {especie.label.upper()} de {quantidade}"
        )
        self.ajuste_aplicar_button.setEnabled(self._pode_movimentar)

    def _atualizar_detalhe(self, *_):
        """O placeholder diz quando o detalhe deixa de ser opcional."""
        motivo = self.ajuste_motivo_combo.currentData()
        obrigatorio = bool(motivo and motivo.exige_detalhe)
        self.ajuste_detalhe_input.setPlaceholderText(
            "Justificativa (obrigatória para \"Outro\")" if obrigatorio
            else "Detalhe (opcional)"
        )

    def _aplicar_ajuste(self):
        """Valida o que a tela sabe e pede. A recusa que vale é do serviço."""
        from stockflow.application.dto.adjustment_input import AdjustmentInput

        codigo = self.ajuste_produto_combo.currentData()
        atual = self._saldo_do_produto_de_ajuste()
        if not codigo or atual is None:
            self.warning_label.setText("Selecione um produto ativo para ajustar.")
            return

        motivo = self.ajuste_motivo_combo.currentData()
        detalhe = self.ajuste_detalhe_input.text().strip()
        if motivo.exige_detalhe and not detalhe:
            self.warning_label.setText(
                'O motivo "Outro" exige uma justificativa escrita.'
            )
            return

        self.warning_label.setText("")
        self.adjust_requested.emit(AdjustmentInput(
            product_code=codigo,
            counted_balance=self.ajuste_contado_input.value(),
            # O saldo que ESTA tela exibiu. É ele que a função compara com o
            # saldo real para detectar que outra pessoa movimentou o produto
            # entre a contagem e o clique.
            expected_balance=atual,
            reason=motivo,
            detail=detalhe,
        ))

    def limpar_ajuste(self):
        self.ajuste_contado_input.setValue(0)
        self.ajuste_detalhe_input.clear()
        self.ajuste_motivo_combo.setCurrentIndex(0)
        self.warning_label.setText("")
        self._atualizar_previa()

    def mostrar_recusa_de_ajuste(self, mensagem):
        self.warning_label.setText(str(mensagem))
```

- [ ] **Step 5: Feed the product combo and the permission toggle**

At the end of `reload_products`, mirror the offer into the adjustment combo:

```python
        atual_ajuste = self.ajuste_produto_combo.currentData()
        self.ajuste_produto_combo.clear()
        self.ajuste_produto_combo.addItem("Selecione um produto...", None)
        for produto in selectable_products(self.products):
            self.ajuste_produto_combo.addItem(
                f"{produto.code} — {produto.name}", produto.code
            )
        if atual_ajuste is not None:
            indice = self.ajuste_produto_combo.findData(atual_ajuste)
            if indice >= 0:
                self.ajuste_produto_combo.setCurrentIndex(indice)
        self._atualizar_previa()
```

`reload_products` runs in `__init__` before `_create_adjustment_form` would
exist if the card were built later — it is not: `_create_adjustment_form` is
called from the layout block, which runs before `self.reload_products(...)` at
the end of `__init__`. Keep that order.

In `apply_permission`, extend the widget tuple:

```python
        for widget in (self.produto_combo, self.especie_combo,
                       self.quantidade_input, self.nota_input,
                       self.fornecedor_combo,
                       self.registrar_button, self.registrar_confirmar_button,
                       self.ajuste_produto_combo, self.ajuste_contado_input,
                       self.ajuste_motivo_combo, self.ajuste_detalhe_input,
                       self.ajuste_aplicar_button):
            widget.setEnabled(self._pode_movimentar)
```

And after `self._update_supplier_enabled()`, add `self._atualizar_previa()` so
the button never comes back enabled for a role that cannot write.

Imports at the top of the module:

```python
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.exceptions.adjustment_errors import AjusteSemEfeitoError
from stockflow.domain.stock_adjustment import calcular_ajuste
from stockflow.domain.stock_level import to_int
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_movimentacoes_na_tela.py tests/test_movimentacoes_estoque.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/stockflow/presentation/pages/movimentacoes.py tests/test_movimentacoes_na_tela.py
git commit -m "feat(h11): add manual adjustment card to the movements page"
```

---

### Task 9: Ligar o card à janela

**Files:**
- Modify: `src/stockflow/presentation/windows/main_window.py:284-286,395-420`
- Test: `tests/test_movimentacoes_na_tela.py`

**Atenção ao arquivo:** `tests/test_movimentacoes_estoque.py` NÃO é teste de
interface — é verificação estática do SQL das migrations. A janela de verdade
mora em `tests/test_movimentacoes_na_tela.py`, que já traz a fixture `janela`
(abre a `MainWindow`, chama `show_page("movimentacoes")` e fecha no fim) e a
fixture `sem_dialogos`. Use as duas; não escreva uma terceira fábrica.

**Interfaces:**
- Consumes: `MovimentacoesPage.adjust_requested`,
  `MovementService.adjust`, `SaldoDesatualizadoError`.
- Produces: `MainWindow._aplicar_ajuste(dados)`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_movimentacoes_na_tela.py`:

```python
# ------------------------------------------------------------- ajuste (H11)

def test_ajuste_pela_tela_muda_o_saldo_do_estoque(janela, sem_dialogos):
    """O ciclo inteiro: card → serviço → adaptador → tabela de Estoque.

    Reconsultar o Estoque não é zelo: ajuste muda saldo, saldo muda situação,
    e alerta desatualizado é o que a US04 proíbe.
    """
    from stockflow.domain.enums.adjustment_reason import AdjustmentReason

    w = janela(UserRole.STOCK)
    w.show_page("movimentacoes")
    page = w.movimentacoes_page
    codigo = next(iter(w.products))
    atual = int(w.products[codigo].stock)

    page.ajuste_produto_combo.setCurrentIndex(
        page.ajuste_produto_combo.findData(codigo)
    )
    page.ajuste_contado_input.setValue(atual + 7)
    page.ajuste_motivo_combo.setCurrentIndex(
        page.ajuste_motivo_combo.findData(AdjustmentReason.CONTAGEM)
    )
    page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == atual + 7
    assert page.table.rowCount() >= 1


def test_vendedor_nao_ajusta_nem_burlando_o_botao(janela, sem_dialogos):
    """O controle visual é cortesia; a recusa é do serviço."""
    from stockflow.application.dto.adjustment_input import AdjustmentInput
    from stockflow.domain.enums.adjustment_reason import AdjustmentReason

    w = janela(UserRole.SELLER)
    codigo = next(iter(w.products))
    antes = w.products[codigo].stock

    w._aplicar_ajuste(AdjustmentInput(
        product_code=codigo, counted_balance=0, expected_balance=int(antes),
        reason=AdjustmentReason.PERDA, detail="",
    ))

    assert w.products[codigo].stock == antes
```

As duas fixtures (`janela`, `sem_dialogos`) já existem no topo deste arquivo.
`janela(papel)` devolve a `MainWindow` já em Movimentações.

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_movimentacoes_na_tela.py -k ajuste -q`
Expected: FAIL com `AttributeError: 'MainWindow' object has no attribute '_aplicar_ajuste'`

- [ ] **Step 3: Connect the signal**

Next to the three existing connections (~line 284):

```python
        self.movimentacoes_page.adjust_requested.connect(self._aplicar_ajuste)
```

- [ ] **Step 4: Write the handler**

After `_registrar_movimentacao`:

```python
    def _aplicar_ajuste(self, dados):
        """Ajuste manual: grava e reconsulta, porque o saldo mudou na hora.

        Ao contrário de `_registrar_movimentacao`, não há caso em que o saldo
        fique parado: ajuste nasce confirmado. Então `_saldo_mudou()` é
        incondicional.
        """
        try:
            self.movement_service.adjust(self.session, dados)
        except PermissionDeniedError as erro:
            self.movimentacoes_page.mostrar_recusa_de_ajuste(erro)
            return
        except SaldoDesatualizadoError as erro:
            # Recontagem, não falha: a mensagem já diz os dois saldos, e
            # recarregar o catálogo faz o campo "Saldo atual" mostrar o
            # número novo antes da próxima tentativa.
            self.movimentacoes_page.mostrar_recusa_de_ajuste(erro)
            self._saldo_mudou()
            return
        except ValueError as erro:
            self.movimentacoes_page.mostrar_recusa_de_ajuste(erro)
            return
        except Exception as erro:
            self.last_save_error = erro
            QMessageBox.critical(self, "Não foi possível ajustar", str(erro))
            return

        self.movimentacoes_page.limpar_ajuste()
        self._recarregar_movimentacoes()
        self._saldo_mudou()
```

`SaldoDesatualizadoError` must come **before** `ValueError` in the except
chain — it subclasses `ValueError`, and a broader clause first would swallow
it and skip the catalog refresh.

Import at the top of the module:

```python
from stockflow.domain.exceptions.adjustment_errors import SaldoDesatualizadoError
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q`
Expected: PASS, suíte inteira

- [ ] **Step 6: Commit**

```bash
git add src/stockflow/presentation/windows/main_window.py tests/test_movimentacoes_na_tela.py
git commit -m "feat(h11): wire the adjustment card to the main window"
```

---

### Task 10: Teste de aceitação da história

**Files:**
- Create: `tests/test_h11_ajuste_manual.py`

**Interfaces:**
- Consumes: tudo o que as tasks anteriores produziram.
- Produces: nada. É a prova dos três critérios pelo caminho do usuário.

- [ ] **Step 1: Write the test**

Create `tests/test_h11_ajuste_manual.py`:

```python
"""H11 — ajuste manual conferido pelo caminho do usuário.

Um teste por critério de aceite:

1. permissão — ADMIN e STOCK ajustam; SELLER é recusado, e não só pelo botão
   escondido;
2. justificativa — motivo é obrigatório, e `OUTRO` exige texto; recusa não
   grava nada;
3. saldo resultante — depois do ajuste o saldo é EXATAMENTE o contado.

Mais os casos de borda que costumam escapar: contar zero, contar o mesmo, e o
saldo mudar entre a contagem e o clique.
"""

import pytest
from PySide6.QtWidgets import QMessageBox

from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.adjustment_errors import SaldoDesatualizadoError
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.presentation import backend
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.windows.main_window import MainWindow

PODEM_AJUSTAR = [UserRole.ADMIN, UserRole.STOCK]


@pytest.fixture
def sem_dialogos(monkeypatch):
    """Silencia os QMessageBox modais, que travariam o teste no `exec()`."""
    chamadas = []
    monkeypatch.setattr(
        QMessageBox, "critical",
        staticmethod(lambda *args, **kwargs: chamadas.append(args)),
    )
    return chamadas


@pytest.fixture
def janela(qapp, monkeypatch, sem_dialogos):
    """Fábrica de MainWindow em modo demonstração, fechada no fim do teste."""
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setattr(backend, "_demo_users", {})
    abertas = []

    def abrir(papel):
        # Sem `show_page`: para o SELLER isso dispara o redirecionamento de
        # navegação, que é assunto da H14. Aqui o que se mede é o ajuste, e o
        # card já nasce montado e com a permissão aplicada pela sessão.
        w = MainWindow(session=conta_por_papel(papel).session())
        abertas.append(w)
        return w

    yield abrir
    for w in abertas:
        w.close()


def primeiro_produto(w):
    codigo = next(iter(w.products))
    return codigo, int(w.products[codigo].stock)


def preencher(page, codigo, contado, motivo, detalhe=""):
    page.ajuste_produto_combo.setCurrentIndex(
        page.ajuste_produto_combo.findData(codigo)
    )
    page.ajuste_contado_input.setValue(contado)
    page.ajuste_motivo_combo.setCurrentIndex(
        page.ajuste_motivo_combo.findData(motivo)
    )
    page.ajuste_detalhe_input.setText(detalhe)


# ------------------------------------------------------------- 1. permissão


@pytest.mark.parametrize("papel", PODEM_AJUSTAR)
def test_admin_e_estoquista_ajustam_pelo_card(janela, papel):
    w = janela(papel)
    codigo, atual = primeiro_produto(w)

    preencher(w.movimentacoes_page, codigo, atual + 3, AdjustmentReason.CONTAGEM)
    w.movimentacoes_page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == atual + 3


def test_o_vendedor_nao_ve_o_card_operavel(janela):
    w = janela(UserRole.SELLER)
    page = w.movimentacoes_page

    assert not page.ajuste_aplicar_button.isEnabled()
    assert not page.ajuste_contado_input.isEnabled()


def test_o_vendedor_e_recusado_mesmo_burlando_o_controle_visual(janela):
    """O critério não é "o botão some" — é que a gravação não aconteça.

    O serviço checa antes de tocar no repositório, e no banco
    `fn_register_adjustment` checa `fn_has_role` por conta própria. São
    camadas: esta dá a mensagem, aquela impede.
    """
    w = janela(UserRole.SELLER)
    codigo, atual = primeiro_produto(w)

    with pytest.raises(PermissionDeniedError):
        w.movement_service.adjust(w.session, AdjustmentInput(
            product_code=codigo, counted_balance=0, expected_balance=atual,
            reason=AdjustmentReason.PERDA,
        ))

    assert int(w.products[codigo].stock) == atual


# --------------------------------------------------------- 2. justificativa


def test_outro_sem_detalhe_nao_grava_nada(janela):
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)
    page = w.movimentacoes_page

    preencher(page, codigo, atual - 1, AdjustmentReason.OUTRO, detalhe="")
    page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == atual
    assert "justificativa" in page.warning_label.text().casefold()


def test_outro_com_detalhe_grava_e_o_detalhe_aparece_no_historico(janela):
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)
    page = w.movimentacoes_page

    preencher(page, codigo, atual - 1, AdjustmentReason.OUTRO,
              detalhe="Caixa amassada na doca")
    page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == atual - 1
    observacoes = [
        page.table.item(linha, 4).text() for linha in range(page.table.rowCount())
    ]
    assert "Caixa amassada na doca" in observacoes


def test_o_motivo_aparece_na_coluna_propria(janela):
    """Coluna Motivo, não Observação: motivo é dado agregável, nota é texto."""
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)
    page = w.movimentacoes_page

    preencher(page, codigo, atual - 2, AdjustmentReason.QUEBRA)
    page.ajuste_aplicar_button.click()

    motivos = [
        page.table.item(linha, 7).text() for linha in range(page.table.rowCount())
    ]
    assert AdjustmentReason.QUEBRA.label in motivos


# ------------------------------------------------------ 3. saldo resultante


def test_o_saldo_final_e_exatamente_o_contado(janela):
    w = janela(UserRole.STOCK)
    codigo, _ = primeiro_produto(w)
    page = w.movimentacoes_page

    preencher(page, codigo, 7, AdjustmentReason.CONTAGEM)
    page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == 7


def test_contar_zero_zera_o_saldo(janela):
    """Produto que sumiu inteiro: saída do saldo todo, resultante zero."""
    w = janela(UserRole.STOCK)
    codigo, _ = primeiro_produto(w)
    page = w.movimentacoes_page

    preencher(page, codigo, 0, AdjustmentReason.PERDA)
    page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == 0


def test_contar_o_mesmo_numero_nao_registra_movimentacao(janela):
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)
    page = w.movimentacoes_page
    linhas_antes = page.table.rowCount()

    preencher(page, codigo, atual, AdjustmentReason.CONTAGEM)

    assert not page.ajuste_aplicar_button.isEnabled()
    assert page.table.rowCount() == linhas_antes


def test_saldo_que_mudou_desde_a_contagem_pede_recontagem(janela):
    """A corrida real: a tela mostrou 42, outra pessoa confirmou uma entrada.

    Aplicar a diferença sobre o saldo novo daria um número que não é o
    contado nem o correto.
    """
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)

    with pytest.raises(SaldoDesatualizadoError):
        w.movement_repository.adjust(AdjustmentInput(
            product_code=codigo, counted_balance=atual - 4,
            expected_balance=atual + 10,     # saldo que a tela teria exibido
            reason=AdjustmentReason.QUEBRA,
        ))

    assert int(w.products[codigo].stock) == atual


def test_a_recusa_de_recontagem_chega_ao_card_sem_dialogo(janela):
    """Erro na área do card, nunca em diálogo: diálogo some e some a razão."""
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)

    w._aplicar_ajuste(AdjustmentInput(
        product_code=codigo, counted_balance=atual - 4,
        expected_balance=atual + 10, reason=AdjustmentReason.QUEBRA,
    ))

    assert "reconte" in w.movimentacoes_page.warning_label.text().casefold()
    assert int(w.products[codigo].stock) == atual
```

- [ ] **Step 2: Run the test**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_h11_ajuste_manual.py -q`
Expected: PASS. Se algum caso falhar, o defeito está na implementação das
tasks anteriores — corrija lá, não afrouxe a asserção.

- [ ] **Step 3: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_h11_ajuste_manual.py
git commit -m "test(h11): cover permission, justification and resulting balance end to end"
```

---

### Task 11: Verificação contra PostgreSQL real

Teste com cliente falso não prova schema nenhum. Esta task é a que prova que o
SQL aplica e que a função se comporta como o resto do plano assume.

**Files:**
- Modify: `scripts/verify_postgres.py`

**Interfaces:**
- Consumes: a migration da Task 3 e a fonte declarativa da Task 2.
- Produces: bloco de verificação H11 no script.

- [ ] **Step 1: Start a local PostgreSQL**

```bash
SP=/tmp/claude-1000/h11-pg
mkdir -p "$SP" /tmp/sfpg
SRC=$(uv run --with pgserver python -c "import pgserver,os;print(os.path.dirname(pgserver.__file__))")
cp -a "$SRC/pginstall" "$SP/pg"
# O build do pgserver não tem contrib, e procedures/06_cash_register.sql faz
# CREATE EXTENSION pgcrypto. O stub vai na CÓPIA, que morre com o scratchpad.
cat > "$SP/pg/share/postgresql/extension/pgcrypto.control" <<'EOF'
comment = 'stub'
default_version = '1.3'
relocatable = true
EOF
cat > "$SP/pg/share/postgresql/extension/pgcrypto--1.3.sql" <<'EOF'
CREATE FUNCTION gen_salt(text) RETURNS text AS $$ SELECT '$stub$' $$ LANGUAGE sql;
CREATE FUNCTION crypt(text, text) RETURNS text AS $$ SELECT '$stub$' || md5($1) $$ LANGUAGE sql;
EOF
export LD_LIBRARY_PATH="$SRC/../pgserver.libs:$SP/pg/lib"
"$SP/pg/bin/initdb" -D "$SP/pgdata" -U postgres -A trust
"$SP/pg/bin/pg_ctl" -D "$SP/pgdata" -o "-k /tmp/sfpg -h 127.0.0.1 -p 55439" -l "$SP/pg.log" start
```

Expected: `server started`. O socket vai em `/tmp/sfpg` porque o caminho do
scratchpad estoura o limite de 107 bytes do socket Unix — e o Postgres loga
`listening on IPv4` e morre mesmo assim.

- [ ] **Step 2: Add the H11 block to the verification script**

`scripts/verify_postgres.py` já tem o idioma pronto; siga-o em vez de inventar
outro. Os rótulos deste arquivo são em **inglês**, as conexões são
`autocommit=True` (então statement recusado NÃO aborta transação e não há
`rollback` a fazer), e os helpers são:

```python
check(condition, label)                  # imprime PASS ou levanta
rejects(lambda: ..., '42501', label)     # exige que levante COM aquele sqlstate
rpc(name, **args)                        # RPC pela conexão do ADMIN
connect('seller_auth')                   # conexão autenticada como SELLER
admin.execute(...)                       # conexão independente, fora da RPC
```

Insira o bloco dentro de `exercise(dsn)`, **imediatamente antes do comentário
`# H14: profiles and permissions`**:

```python
    # H11: manual stock adjustment. This runs BEFORE the H14 block, which
    # promotes the STOCK account to ADMIN — an adjustment checked after that
    # would no longer be measuring the STOCK role.
    #
    # What only Postgres decides: the role check inside the function, the
    # justification CHECK, the stale-balance refusal, and above all that the
    # resulting balance equals the counted one when read from OUTSIDE the
    # transaction that wrote it. `admin` is that independent connection.
    before=admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]
    rpc('fn_register_adjustment',p_company_id=company,p_product_id=str(product_id),
        p_counted_balance=before-3,p_expected_balance=before,p_reason='QUEBRA',
        p_detail='caixa amassada')
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==before-3,
          'Adjustment leaves the balance exactly at the counted value')
    check(admin.execute('SELECT kind,quantity,status,adjustment_reason,counted_balance '
                        'FROM stock_movements WHERE product_id=%s '
                        'ORDER BY created_on DESC LIMIT 1',(product_id,)).fetchone()
          ==('SAIDA',3,'CONFIRMADA','QUEBRA',before-3),
          'Adjustment is a confirmed movement carrying reason and counted balance')
    check(admin.execute('SELECT created_by FROM stock_movements WHERE product_id=%s '
                        'ORDER BY created_on DESC LIMIT 1',(product_id,)).fetchone()[0]==ids['user'],
          'Adjustment records the authenticated user, never a caller-supplied id')
    rejects(lambda:rpc('fn_register_adjustment',p_company_id=company,p_product_id=str(product_id),
                       p_counted_balance=before-4,p_expected_balance=before-3,
                       p_reason='OUTRO',p_detail=None),
            '23514','Reason OUTRO without a written justification is refused')
    rejects(lambda:rpc('fn_register_adjustment',p_company_id=company,p_product_id=str(product_id),
                       p_counted_balance=before-3,p_expected_balance=before-3,
                       p_reason='CONTAGEM',p_detail=None),
            '23514','Counting the same balance registers nothing')
    rejects(lambda:rpc('fn_register_adjustment',p_company_id=company,p_product_id=str(product_id),
                       p_counted_balance=1,p_expected_balance=before+99,
                       p_reason='CONTAGEM',p_detail=None),
            '40001','A balance that moved since the count asks for a recount')
    with connect('seller_auth') as seller:
        rejects(lambda:PostgresAPI(seller).rpc('fn_register_adjustment',
                    {'p_company_id':company,'p_product_id':str(product_id),
                     'p_counted_balance':0,'p_expected_balance':before-3,
                     'p_reason':'PERDA','p_detail':None}).execute(),
                '42501','A seller cannot adjust stock')
    check(admin.execute('SELECT stock FROM products WHERE id=%s',(product_id,)).fetchone()[0]==before-3,
          'Every refused adjustment left the balance untouched')
```

A última linha é a que fecha o critério: quatro recusas depois, o saldo é o
mesmo do único ajuste aceito. Recusa que grava metade não seria recusa.

- [ ] **Step 3: Run both verification modes**

```bash
export STOCKFLOW_TEST_DSN='host=127.0.0.1 port=55439 dbname=postgres user=postgres'
uv run python scripts/verify_postgres.py
uv run python scripts/verify_postgres.py --schema
```

Expected: os dois saem com código 0 e imprimem os `PASS` do bloco H11. Os dois
modos aplicam fontes diferentes — `migrations/` e `code/` — e passar nos dois é
o que prova que a migration é fiel à fonte declarativa.

- [ ] **Step 4: Rehearse the incremental application**

Aplicar em banco limpo não prova `supabase db push`. Simule o remoto: aplique
todas as migrations **anteriores** à da H11, insira dado preexistente, e só
então aplique a nova por cima.

```bash
PSQL="$SP/pg/bin/psql -h 127.0.0.1 -p 55439 -U postgres -v ON_ERROR_STOP=1"
"$SP/pg/bin/dropdb"   -h 127.0.0.1 -p 55439 -U postgres --if-exists ensaio
"$SP/pg/bin/createdb" -h 127.0.0.1 -p 55439 -U postgres ensaio

for f in $(ls database/supabase/migrations/*.sql | grep -v h11_manual_stock_adjustment); do
  $PSQL -d ensaio -f "$f" || { echo "FALHOU: $f"; break; }
done

# Dado preexistente: um produto com saldo composto por duas movimentações
# confirmadas. É sobre ELE que o ADD COLUMN com CHECK tem que passar.
$PSQL -d ensaio <<'SQL'
INSERT INTO company(id,name)
     VALUES ('11111111-1111-1111-1111-111111111111','Ensaio');
INSERT INTO products(id,company_id,barcode,name,sell_price)
     VALUES ('22222222-2222-2222-2222-222222222222',
             '11111111-1111-1111-1111-111111111111','ENS-001','Arroz 5kg','10.00');
INSERT INTO stock_movements(company_id,product_id,kind,quantity,status,confirmed_on)
     VALUES ('11111111-1111-1111-1111-111111111111',
             '22222222-2222-2222-2222-222222222222','ENTRADA',40,'CONFIRMADA',now()),
            ('11111111-1111-1111-1111-111111111111',
             '22222222-2222-2222-2222-222222222222','SAIDA',  5,'CONFIRMADA',now());
SELECT stock AS saldo_antes FROM products
 WHERE id='22222222-2222-2222-2222-222222222222';
SQL

$PSQL -d ensaio -f database/supabase/migrations/*h11_manual_stock_adjustment.sql

$PSQL -d ensaio <<'SQL'
SELECT stock AS saldo_depois FROM products
 WHERE id='22222222-2222-2222-2222-222222222222';
SELECT count(*) AS movimentacoes_preservadas,
       count(*) FILTER (WHERE adjustment_reason IS NULL) AS sem_marca_de_ajuste
  FROM stock_movements;
SQL
```

Expected: `saldo_antes` e `saldo_depois` ambos **35**; `movimentacoes_preservadas`
= 2 e `sem_marca_de_ajuste` = 2. As linhas antigas ficam com
`adjustment_reason IS NULL`, que é o lado permitido do CHECK `pair`.

Se o CHECK recusar dado antigo, **a migration está errada** — conserte a
migration, nunca o dado.

- [ ] **Step 5: Stop the server and record the result**

```bash
"$SP/pg/bin/pg_ctl" -D "$SP/pgdata" stop
```

Anote no relatório final que o stub de `pgcrypto` **não testa criptografia**.

- [ ] **Step 6: Commit**

```bash
git add scripts/verify_postgres.py
git commit -m "test(h11): verify manual adjustment against a real postgres"
```

---

### Task 12: README e baseline visual

**Files:**
- Modify: `README.md`
- Test: `scripts/check_visual.py`

- [ ] **Step 1: Compare the screens against `main`**

O card novo muda o layout de Movimentações, então o baseline muda de
propósito. Capture os dois lados a partir de uma árvore separada — nunca
`git stash`, que mexeria no trabalho em andamento:

```bash
git worktree add /tmp/stockflow-baseline main
(cd /tmp/stockflow-baseline && uv run python scripts/check_visual.py /tmp/stockflow-before)
uv run python scripts/check_visual.py /tmp/stockflow-after --baseline /tmp/stockflow-before
git worktree remove /tmp/stockflow-baseline
```

Expected: código de saída diferente de zero, com diferenças **apenas** nas
capturas da página de Movimentações. Diferença em qualquer outra tela é
regressão não intencional — investigue antes de seguir.

Relate o diff como mudança aceita, nomeando as capturas que mudaram. Não
silencie o código de saída.

- [ ] **Step 2: Document the flow in the README**

In the **Movimentações** section, after the status table, add:

```markdown
**Ajuste manual** (H11) é o segundo card da tela, e responde a outra
pergunta: não "o que entrou ou saiu", mas "o que existe". O operador escolhe
o produto, informa o **saldo contado** e o **motivo**; o sistema calcula a
diferença e lança a entrada ou a saída correspondente, já confirmada.

| Campo | Regra |
|---|---|
| Saldo contado | inteiro ≥ 0; igual ao atual não gera lançamento |
| Motivo | obrigatório, de lista fechada |
| Detalhe | obrigatório apenas quando o motivo é `Outro` |

Ajuste é operação de ADMIN e STOCK, a mesma alçada das demais movimentações —
`fn_register_adjustment` checa `fn_has_role(ADMIN, STOCK)` por conta própria.

Três coisas que a função garante e a tela não teria como garantir sozinha:
ela trava o produto com `FOR UPDATE`, recusa se o saldo mudou desde que a
tela carregou (pedindo recontagem, em vez de aplicar uma diferença sobre um
número velho) e **relê o saldo depois de gravar** para conferir que ele ficou
exatamente igual ao contado — se não ficou, a transação inteira volta atrás.

Ajuste não é uma terceira espécie de movimentação: é uma `ENTRADA` ou `SAIDA`
comum marcada pela coluna `adjustment_reason`. O saldo continua sendo a soma
das confirmadas, e cancelar um ajuste o devolve, como em qualquer outra.
```

- [ ] **Step 3: Run the whole suite one last time**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(h11): describe the manual adjustment flow"
```

- [ ] **Step 5: Hand the branch to the user — do NOT push**

Show the user `git log --oneline main..HEAD` and the full diff summary, and
ask whether to push and open the PR. The `main` branch requires a pull
request; direct push only works through the owner's bypass.

Include in the handoff:

- which checks ran and their output (suite, both `verify_postgres.py` modes,
  the incremental rehearsal);
- that the `pgcrypto` stub does not test cryptography;
- the exact command for the user to apply the migration themselves:

```bash
cd database && supabase link --project-ref "$SUPABASE_PROJECT_REF" && supabase db push
```

---

## Notas de execução

**Ordem das tasks.** 1 → 2 → 3 estabelecem domínio e banco; 4 é independente e
pode ir a qualquer momento antes de 6; 5 → 6 → 7 → 8 → 9 sobem a pilha; 10 é a
prova; 11 e 12 fecham. Nenhuma task depende de uma posterior.

**Se um teste antigo quebrar na Task 4**, é esperado: o contrato da tupla
mudou de propósito. Ajuste o teste para os índices fixos; não restaure a cauda
opcional.

**Se o `declarative sync` propuser derrubar algo na Task 2**, a causa quase
sempre é `code/` e `schemas/` fora de sincronia. `diff -r database/code
database/supabase/schemas` tem que sair vazio.
