# US17 — Histórico de vendas: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar consulta paginada e filtrável do histórico de vendas, tela de detalhe por venda, e as operações de cancelamento e devolução com reversão de estoque.

**Architecture:** Uma função SQL `SECURITY DEFINER` concentra consulta, filtros, ordenação e paginação, devolvendo a página e o total numa leitura só. Duas funções irmãs fazem a reversão, gravando o vínculo em `sale_reversals` e movendo o estoque por movimentação (nunca escrevendo `products.stock`). A aplicação ganha a porta `SaleRepository` que faltava, e a interface ganha filtros, paginação, coluna de status e uma página de detalhe onde moram as ações destrutivas.

**Tech Stack:** Python 3.12, PySide6, PostgreSQL 16 (Supabase), psycopg 3, pytest.

**Spec:** `docs/superpowers/specs/2026-10-24-us17-historico-de-vendas-design.md`

## Global Constraints

- **Comentário de código e texto de interface em português.** Artefatos de Git (branch, commit, PR) em inglês.
- **Commits exigem confirmação do usuário.** Política da organização: nunca commitar nem fazer push sem o usuário confirmar arquivos e mensagem. Os passos "Commit" deste plano preparam o commit e **param para confirmação**.
- **Migration nunca é aplicada no Supabase pelo executor.** Escrever, verificar contra PostgreSQL local, entregar o comando.
- **O schema é espelho triplo.** Todo objeto novo em `database/code/`, na migration, e em `database/supabase/schemas/` como cópia byte a byte. O espelho é gerado por sync, nunca editado à mão.
- **Guarda de permissão é a primeira instrução** de todo método de serviço, antes de qualquer acesso ao repositório.
- **Função SQL de escrita resolve `company_id` da linha persistida**, nunca por parâmetro do chamador.
- **Saldo muda registrando movimentação**, nunca por `UPDATE products.stock`.
- **Verificação de teste sempre escopada:** `pytest tests/`. `pytest` sem caminho coleta `docs/` e não é verificação válida neste repositório.
- **Baseline da suíte em 2026-10-24:** `1074 passed, 27 skipped`. Toda entrega é confrontada com ele.
- Comando base: `.venv/bin/python -m pytest tests/ -q`
- PostgreSQL local para verificação: ver `scripts/verify_sales.py` e a receita de `pgserver` na memória do projeto.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `database/code/tables/06_clients_sales.sql` | Enum `DEVOLVIDA`, enum `sale_reversal_kind`, tabela `sale_reversals` |
| `database/code/procedures/07_clients_sales.sql` | `fn_list_sales`, `fn_cancel_sale`, `fn_return_sale` |
| `database/code/policies/01_security.sql` | RLS, grant, policy e allowlist de EXECUTE da tabela e das funções novas |
| `database/supabase/migrations/20261024120000_us17_sales_history.sql` | Migration com os mesmos objetos |
| `src/stockflow/domain/enums/sale_status.py` | Espelho do enum de situação da venda |
| `src/stockflow/domain/enums/sale_reversal_kind.py` | Espelho do enum de espécie de reversão |
| `src/stockflow/domain/permissions.py` | Área `vendas_reversao` |
| `src/stockflow/application/dto/sale_filter.py` | `SaleFilter` e `SalePage` |
| `src/stockflow/application/ports/sale_repository.py` | Contrato de persistência de vendas |
| `src/stockflow/application/services/sale_service.py` | Consulta com sessão, detalhe, cancelar, devolver |
| `src/stockflow/infrastructure/repositories/demo_sale_repository.py` | Mesma semântica em memória |
| `src/stockflow/infrastructure/repositories/supabase_sale_repository.py` | Chamadas RPC |
| `src/stockflow/presentation/pages/vendas.py` | Filtros, ordenação, paginação, coluna de status |
| `src/stockflow/presentation/pages/sale_details.py` | Página de detalhe e ações de reversão |
| `src/stockflow/presentation/windows/main_window.py` | Navegação, reversão e atualização do estoque |
| `src/stockflow/presentation/pages/dashboard.py` | Excluir vendas revertidas do total |
| `src/stockflow/presentation/pages/reports.py` | Excluir vendas revertidas do total |

---

### Task 1: Tabela de reversão e enums no banco

**Files:**
- Modify: `database/code/tables/06_clients_sales.sql:113` (após o `CREATE TYPE public.sale_status`)
- Modify: `database/code/policies/01_security.sql:28-33, 60-74, 89-94, 120-133`
- Create: `database/supabase/migrations/20261024120000_us17_sales_history.sql`
- Test: `tests/test_schema_declarativo.py`

**Interfaces:**
- Produces: tipo `public.sale_status` com valor `DEVOLVIDA`; tipo `public.sale_reversal_kind` com `CANCELAMENTO` e `DEVOLUCAO`; tabela `public.sale_reversals (id, company_id, sale_id, kind, reason, created_by, created_on)`; policy `sale_reversals_select`.

- [ ] **Step 1: Write the failing test**

Acrescentar ao fim de `tests/test_schema_declarativo.py`:

```python
# --------------------------------------------------------------------- US17
# A reversão de venda é uma RELAÇÃO, não um atributo do cabeçalho. Estes
# testes cobram que a tabela de vínculo e os dois enums estejam na FONTE
# declarativa: `code/` é o que o declarative sync diffa contra o banco, e o
# que ficar de fora dele o diff seguinte propõe derrubar.


def test_us17_status_de_venda_inclui_devolvida():
    assert "ADD VALUE IF NOT EXISTS 'DEVOLVIDA'" in CODE_SQL


def test_us17_especie_de_reversao_tem_os_dois_valores():
    achado = re.search(
        r"CREATE TYPE public\.sale_reversal_kind AS ENUM\s*\((.*?)\)",
        CODE_SQL, re.S,
    )
    assert achado, "tipo public.sale_reversal_kind não declarado em database/code"
    assert set(re.findall(r"'(\w+)'", achado.group(1))) == {
        "CANCELAMENTO", "DEVOLUCAO"
    }


def test_us17_reversao_e_terminal_por_indice_unico():
    """Venda revertida não vira outra coisa depois.

    A função também confere, mas o UNIQUE é o que torna a regra verdadeira
    para quem chegue por outro caminho.
    """
    corpo = re.search(
        r"CREATE TABLE public\.sale_reversals\s*\((.*?)\n\);", CODE_SQL, re.S
    )
    assert corpo, "tabela sale_reversals não encontrada em database/code"
    assert "UNIQUE (sale_id)" in corpo.group(1)


def test_us17_reversao_escopa_por_coluna_propria():
    corpo = re.search(
        r"CREATE TABLE public\.sale_reversals\s*\((.*?)\n\);", CODE_SQL, re.S
    ).group(1)
    assert "company_id  uuid NOT NULL" in corpo
    assert "REFERENCES public.sales (company_id, id) ON DELETE CASCADE" in corpo


def test_us17_reversao_exige_motivo_nao_vazio():
    corpo = re.search(
        r"CREATE TABLE public\.sale_reversals\s*\((.*?)\n\);", CODE_SQL, re.S
    ).group(1)
    assert "CHECK (btrim(reason) <> '')" in corpo


def test_us17_aplicacao_nao_escreve_na_tabela_de_reversao():
    """Mesma proteção de `sales`: só SELECT. A escrita é das funções."""
    politicas = (CODE / "policies" / "01_security.sql").read_text(encoding="utf-8")
    assert "public.sale_reversals" in politicas.split("GRANT SELECT ON", 1)[1].split(";", 1)[0]
    assert "CREATE POLICY sale_reversals_select ON public.sale_reversals" in politicas
    assert "FOR SELECT TO app_backend, authenticated" in politicas
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_schema_declarativo.py -k us17 -q`
Expected: FAIL — `tipo public.sale_reversal_kind não declarado em database/code`

- [ ] **Step 3: Declarar o tipo e a tabela na fonte**

Em `database/code/tables/06_clients_sales.sql`, logo depois do bloco do `payment_method` (linha 119) e antes do `CREATE TABLE public.sales`:

```sql
-- Situação de venda revertida. `ADD VALUE` e não recriação do enum: o tipo
-- já existe no remoto com três rótulos, e `CREATE TYPE` ali falharia.
ALTER TYPE public.sale_status ADD VALUE IF NOT EXISTS 'DEVOLVIDA';

-- Cancelar e devolver não são a mesma coisa, e a diferença precisa
-- sobreviver no registro: cancelamento diz que a venda não deveria ter
-- existido; devolução diz que existiu e a mercadoria voltou.
CREATE TYPE public.sale_reversal_kind AS ENUM ('CANCELAMENTO', 'DEVOLUCAO');
```

E ao fim do arquivo, depois de `sales_log`:

```sql
-- Vínculo entre a venda original e a operação que a desfez (US17).
--
-- Tabela, e não colunas em `sales`: o vínculo é uma RELAÇÃO com autor,
-- motivo e instante próprios. Como atributo do cabeçalho ele engordaria a
-- cada motivo novo e não teria onde guardar autoria separada da autoria da
-- venda. Mesmo papel que `sales_log` cumpre para a conclusão.
CREATE TABLE public.sale_reversals (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Redundante com sales.company_id, e proposital: a policy escopa por
    -- esta coluna sem entrar em `sales` a cada linha, como em sale_items.
    company_id  uuid NOT NULL,
    sale_id     uuid NOT NULL,
    kind        public.sale_reversal_kind NOT NULL,
    reason      text NOT NULL CHECK (btrim(reason) <> ''),
    -- Sem FK, como sales.created_by: a autoria da reversão precisa
    -- sobreviver à remoção da conta que a fez.
    created_by  uuid,
    created_on  timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE CASCADE,
    -- Reversão é TERMINAL: venda cancelada não vira devolvida depois, nem
    -- acumula reversões. A função confere também, mas é este índice que
    -- torna a regra verdadeira para quem chegue por outro caminho.
    UNIQUE (sale_id)
);
CREATE INDEX idx_sale_reversals_company ON public.sale_reversals (company_id);
```

- [ ] **Step 4: Abrir a leitura na política de segurança**

Em `database/code/policies/01_security.sql`:

1. Depois da linha 30 (`ALTER TABLE public.sales_log ENABLE ROW LEVEL SECURITY;`):

```sql
ALTER TABLE public.sale_reversals ENABLE ROW LEVEL SECURITY;
```

2. Na lista do `GRANT SELECT` (linha 69, depois de `public.sales_log,`):

```sql
                public.sale_reversals,
```

3. Junto dos outros `DROP POLICY IF EXISTS` (linha 91):

```sql
DROP POLICY IF EXISTS sale_reversals_select  ON public.sale_reversals;
```

4. Depois da policy `sales_log_select` (linha 133):

```sql
-- Mesma proteção de `sales`: SELECT e nada mais. A escrita é exclusiva de
-- fn_cancel_sale/fn_return_sale, que são SECURITY DEFINER. Dar INSERT aqui
-- deixaria a aplicação forjar o vínculo que a auditoria deveria provar.
CREATE POLICY sale_reversals_select ON public.sale_reversals
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));
```

- [ ] **Step 5: Espelhar em `database/supabase/schemas/`**

```bash
cp database/code/tables/06_clients_sales.sql database/supabase/schemas/tables/06_clients_sales.sql
cp database/code/policies/01_security.sql database/supabase/schemas/policies/01_security.sql
```

- [ ] **Step 6: Escrever a migration**

Criar `database/supabase/migrations/20261024120000_us17_sales_history.sql` com o MESMO conteúdo dos objetos novos, tolerante a reexecução:

```sql
-- US17: vínculo de cancelamento e devolução de venda.
--
-- Sem BEGIN/COMMIT próprios: `ALTER TYPE ... ADD VALUE` convive mal com
-- transação explícita, e nenhum comando aqui exige uma. Segue o mesmo
-- caminho de 20261013140000, que já acrescentou 'CANCELADA' a este enum.

ALTER TYPE public.sale_status ADD VALUE IF NOT EXISTS 'DEVOLVIDA';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sale_reversal_kind') THEN
        CREATE TYPE public.sale_reversal_kind AS ENUM ('CANCELAMENTO', 'DEVOLUCAO');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.sale_reversals (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL,
    sale_id     uuid NOT NULL,
    kind        public.sale_reversal_kind NOT NULL,
    reason      text NOT NULL CHECK (btrim(reason) <> ''),
    created_by  uuid,
    created_on  timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE CASCADE,
    UNIQUE (sale_id)
);
CREATE INDEX IF NOT EXISTS idx_sale_reversals_company
    ON public.sale_reversals (company_id);

ALTER TABLE public.sale_reversals ENABLE ROW LEVEL SECURITY;
GRANT SELECT ON public.sale_reversals TO app_backend, authenticated;

DROP POLICY IF EXISTS sale_reversals_select ON public.sale_reversals;
CREATE POLICY sale_reversals_select ON public.sale_reversals
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_schema_declarativo.py tests/test_database_migrations.py -q`
Expected: PASS. Em especial `test_code_cobre_todos_os_objetos_das_migrations`, `test_code_nao_inventa_objetos_fora_das_migrations` e `test_schemas_e_espelho_exato_de_code`.

Se `test_code_nao_inventa_objetos_fora_das_migrations` falhar, o objeto está em `code/` mas não na migration (ou vice-versa) — comparar as duas listas antes de mexer em outra coisa.

- [ ] **Step 8: Commit (preparar e confirmar com o usuário)**

```bash
git add database/code/tables/06_clients_sales.sql \
        database/code/policies/01_security.sql \
        database/supabase/schemas/ \
        database/supabase/migrations/20261024120000_us17_sales_history.sql \
        tests/test_schema_declarativo.py
```
Mensagem proposta: `feat(db): add sale reversal link table and DEVOLVIDA status`
**Parar e pedir confirmação do usuário antes de `git commit`.**

---

### Task 2: `fn_list_sales` — consulta paginada e filtrável

**Files:**
- Modify: `database/code/procedures/07_clients_sales.sql` (ao fim)
- Modify: `database/code/policies/01_security.sql:206` (allowlist)
- Modify: `database/supabase/migrations/20261024120000_us17_sales_history.sql`
- Test: `tests/test_schema_declarativo.py`

**Interfaces:**
- Consumes: `public.sale_reversals` (Task 1).
- Produces: `public.fn_list_sales(p_company_id uuid, p_sale_id text, p_from timestamptz, p_to timestamptz, p_client_id uuid, p_seller_id uuid, p_status public.sale_status, p_sort text, p_limit integer, p_offset integer)` retornando as colunas `id, client_id, client_name, seller_id, seller_name, payment_method, discount, total, status, created_on, items, reversal_kind, reversal_reason, reversal_on, reversal_by_name, total_count`.

- [ ] **Step 1: Write the failing test**

Acrescentar a `tests/test_schema_declarativo.py`:

```python
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
    corpo = corpo_da_funcao("fn_list_sales")
    assert "count(*) OVER ()" in corpo


def test_us17_consulta_desempata_a_ordem_pelo_id():
    """Duas vendas no mesmo instante têm ordem indefinida sem desempate, e a
    página seguinte repetiria ou pularia linha."""
    corpo = corpo_da_funcao("fn_list_sales")
    assert re.search(r"ORDER BY.*?f\.id DESC", corpo, re.S)


def test_us17_ordenacao_nunca_e_sql_dinamico():
    """Texto do chamador virando ORDER BY é injeção."""
    corpo = corpo_da_funcao("fn_list_sales")
    assert "EXECUTE" not in corpo.upper().replace("SECURITY DEFINER", "")
    for criterio in ("DATA_DESC", "DATA_ASC", "VALOR_DESC", "VALOR_ASC", "CLIENTE_ASC"):
        assert criterio in corpo


def test_us17_todos_os_filtros_sao_opcionais_e_combinaveis():
    corpo = corpo_da_funcao("fn_list_sales")
    for parametro, coluna in (
        ("p_from", "s.created_on >="),
        ("p_to", "s.created_on <"),
        ("p_client_id", "s.client_id ="),
        ("p_seller_id", "s.created_by ="),
        ("p_status", "s.status ="),
    ):
        assert f"{parametro} IS NULL OR {coluna}" in corpo, parametro


def test_us17_consulta_esta_na_allowlist_de_execute():
    politicas = (CODE / "policies" / "01_security.sql").read_text(encoding="utf-8")
    allowlist = politicas.split("v_names text[] := ARRAY[", 1)[1].split("];", 1)[0]
    assert "'fn_list_sales'" in allowlist
```

E o auxiliar, junto dos outros helpers do arquivo:

```python
def corpo_da_funcao(nome: str) -> str:
    """Texto de uma função em database/code, do CREATE ao próximo CREATE."""
    achado = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{nome}\b(.*?)(?=CREATE OR REPLACE|\Z)",
        CODE_SQL, re.S,
    )
    return achado.group(1) if achado else ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_schema_declarativo.py -k "us17_consulta or us17_ordenacao or us17_todos" -q`
Expected: FAIL — `fn_list_sales não declarada em database/code`

- [ ] **Step 3: Escrever a função na fonte declarativa**

Ao fim de `database/code/procedures/07_clients_sales.sql`:

```sql
-- ------------------------------------------- histórico de vendas (US17)
--
-- Consulta paginada, filtrável e ordenável. Concentrada numa função, e não
-- montada no cliente, por dois motivos: `max_rows` do PostgREST corta a
-- listagem em 1000 linhas sem avisar, e dois adaptadores (Supabase e
-- demonstração) montando filtro cada um do seu jeito divergem em silêncio.
CREATE OR REPLACE FUNCTION public.fn_list_sales(
    p_company_id uuid,
    p_sale_id    text               DEFAULT NULL,
    p_from       timestamptz        DEFAULT NULL,
    p_to         timestamptz        DEFAULT NULL,
    p_client_id  uuid               DEFAULT NULL,
    p_seller_id  uuid               DEFAULT NULL,
    p_status     public.sale_status DEFAULT NULL,
    p_sort       text               DEFAULT 'DATA_DESC',
    p_limit      integer            DEFAULT 50,
    p_offset     integer            DEFAULT 0
)
RETURNS TABLE (
    id               uuid,
    client_id        uuid,
    client_name      text,
    seller_id        uuid,
    seller_name      text,
    payment_method   public.payment_method,
    discount         numeric,
    total            numeric,
    status           public.sale_status,
    created_on       timestamptz,
    items            jsonb,
    reversal_kind    public.sale_reversal_kind,
    reversal_reason  text,
    reversal_on      timestamptz,
    reversal_by_name text,
    total_count      bigint
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
-- Os nomes de RETURNS TABLE viram variáveis e competem com os nomes de
-- coluna. Toda referência abaixo é qualificada, e esta diretiva é a rede
-- para a próxima linha que alguém acrescentar sem qualificar.
#variable_conflict use_column
BEGIN
    -- SECURITY DEFINER passa por cima da RLS, então a checagem que
    -- `sales_select` faz na tabela precisa ser repetida aqui.
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Sem permissão para consultar o histórico desta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF p_limit IS NULL OR p_limit <= 0 OR p_limit > 200 THEN
        RAISE EXCEPTION 'Tamanho de página inválido: %', p_limit
            USING ERRCODE = 'check_violation';
    END IF;
    IF p_offset IS NULL OR p_offset < 0 THEN
        RAISE EXCEPTION 'Deslocamento de página inválido: %', p_offset
            USING ERRCODE = 'check_violation';
    END IF;
    IF p_sort IS NULL OR p_sort NOT IN
       ('DATA_DESC', 'DATA_ASC', 'VALOR_DESC', 'VALOR_ASC', 'CLIENTE_ASC') THEN
        RAISE EXCEPTION 'Ordenação desconhecida: %', p_sort
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN QUERY
    WITH filtradas AS (
        SELECT s.*
          FROM public.sales s
         WHERE s.company_id = p_company_id
           -- Casa por PREFIXO: é como a tela mostra o identificador, e
           -- digitar o uuid inteiro para achar uma venda não é consulta.
           AND (p_sale_id   IS NULL OR s.id::text LIKE lower(btrim(p_sale_id)) || '%')
           AND (p_from      IS NULL OR s.created_on >= p_from)
           -- Limite superior EXCLUSIVO: o chamador manda o início do dia
           -- seguinte, e assim o último dia do período entra inteiro.
           AND (p_to        IS NULL OR s.created_on <  p_to)
           AND (p_client_id IS NULL OR s.client_id = p_client_id)
           AND (p_seller_id IS NULL OR s.created_by = p_seller_id)
           AND (p_status    IS NULL OR s.status = p_status)
    )
    SELECT f.id,
           f.client_id,
           f.client_name,
           f.created_by,
           COALESCE(ua.name, ''),
           f.payment_method,
           f.discount,
           f.total,
           f.status,
           f.created_on,
           COALESCE((SELECT jsonb_agg(to_jsonb(i) ORDER BY i.created_on, i.id)
                       FROM public.sale_items i
                      WHERE i.sale_id = f.id), '[]'::jsonb),
           r.kind,
           r.reason,
           r.created_on,
           COALESCE(rua.name, ''),
           -- Calculado ANTES do LIMIT: é o total que casa com o filtro, que
           -- é o que a tela precisa para saber quantas páginas existem.
           count(*) OVER ()
      FROM filtradas f
      -- LEFT JOIN nos três: a venda pode não ter reversão, e conta removida
      -- não pode apagar a linha do histórico.
      LEFT JOIN public.sale_reversals r   ON r.sale_id = f.id
      LEFT JOIN public.user_accounts  ua  ON ua.id = f.created_by
      LEFT JOIN public.user_accounts  rua ON rua.id = r.created_by
     ORDER BY
        CASE WHEN p_sort = 'DATA_DESC'   THEN f.created_on END DESC,
        CASE WHEN p_sort = 'DATA_ASC'    THEN f.created_on END ASC,
        CASE WHEN p_sort = 'VALOR_DESC'  THEN f.total      END DESC,
        CASE WHEN p_sort = 'VALOR_ASC'   THEN f.total      END ASC,
        CASE WHEN p_sort = 'CLIENTE_ASC' THEN lower(f.client_name) END ASC,
        -- Desempate obrigatório: sem ele a página 2 repete ou pula linha.
        f.id DESC
     LIMIT p_limit OFFSET p_offset;
END;
$$;
```

- [ ] **Step 4: Acrescentar à allowlist de EXECUTE**

Em `database/code/policies/01_security.sql`, na lista `v_names` (linha 206), depois de `'fn_list_price_edits'`:

```sql
    -- Histórico de vendas (US17). Só leitura; a alçada é a mesma de
    -- `sales_select`, repetida dentro da função porque SECURITY DEFINER
    -- passa por cima da RLS.
    'fn_list_sales',
```

- [ ] **Step 5: Espelhar e replicar na migration**

```bash
cp database/code/procedures/07_clients_sales.sql database/supabase/schemas/procedures/07_clients_sales.sql
cp database/code/policies/01_security.sql database/supabase/schemas/policies/01_security.sql
```

Acrescentar o mesmo `CREATE OR REPLACE FUNCTION public.fn_list_sales (...)` à migration `20261024120000_us17_sales_history.sql`, seguido de:

```sql
GRANT EXECUTE ON FUNCTION public.fn_list_sales(
    uuid, text, timestamptz, timestamptz, uuid, uuid,
    public.sale_status, text, integer, integer
) TO app_backend, authenticated;
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_schema_declarativo.py tests/unit/test_permission_matrix.py -q`
Expected: PASS

- [ ] **Step 7: Verificar contra PostgreSQL real**

Subir o PostgreSQL local descartável e aplicar `database/code` como em `scripts/verify_postgres.py --schema`. Conferir que a função cria sem erro — `#variable_conflict` e conflito de nome de coluna só aparecem na criação.

- [ ] **Step 8: Commit (preparar e confirmar com o usuário)**

```bash
git add database/code/procedures/07_clients_sales.sql \
        database/code/policies/01_security.sql \
        database/supabase/schemas/ \
        database/supabase/migrations/20261024120000_us17_sales_history.sql \
        tests/test_schema_declarativo.py
```
Mensagem proposta: `feat(db): add paginated and filterable sales history query`
**Parar e pedir confirmação.**

---

### Task 3: `fn_cancel_sale` e `fn_return_sale`

**Files:**
- Modify: `database/code/procedures/07_clients_sales.sql` (ao fim)
- Modify: `database/code/policies/01_security.sql` (allowlist)
- Modify: `database/supabase/migrations/20261024120000_us17_sales_history.sql`
- Test: `tests/test_schema_declarativo.py`

**Interfaces:**
- Consumes: `public.sale_reversals` (Task 1).
- Produces: `public.fn_cancel_sale(p_sale_id uuid, p_reason text) RETURNS jsonb` e `public.fn_return_sale(p_sale_id uuid, p_reason text) RETURNS jsonb`, ambas devolvendo `{"sale_id", "kind", "reason", "status"}`.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("nome", ["fn_cancel_sale", "fn_return_sale"])
def test_us17_reversao_resolve_a_empresa_pelo_dado_persistido(nome):
    """Padrão do projeto: tenant vem da linha, nunca do chamador."""
    corpo = corpo_da_funcao(nome)
    assert corpo, f"{nome} não declarada em database/code"
    assert "SECURITY DEFINER" in corpo
    assert "FROM public.sales s WHERE s.id = p_sale_id FOR UPDATE" in corpo
    assert "p_company_id" not in corpo


@pytest.mark.parametrize("nome", ["fn_cancel_sale", "fn_return_sale"])
def test_us17_reversao_e_so_do_admin(nome):
    corpo = corpo_da_funcao(nome)
    assert "fn_has_role(v_company, ARRAY['ADMIN']::public.user_role[])" in corpo


@pytest.mark.parametrize("nome", ["fn_cancel_sale", "fn_return_sale"])
def test_us17_reversao_so_aceita_venda_concluida(nome):
    corpo = corpo_da_funcao(nome)
    assert "v_status <> 'CONCLUIDA'" in corpo


@pytest.mark.parametrize("nome", ["fn_cancel_sale", "fn_return_sale"])
def test_us17_reversao_exige_motivo(nome):
    corpo = corpo_da_funcao(nome)
    assert "v_reason = ''" in corpo


def test_us17_cancelamento_anula_a_saida_da_venda():
    """Cancelar devolve o saldo pelo recálculo, que é o padrão do projeto."""
    corpo = corpo_da_funcao("fn_cancel_sale")
    assert "UPDATE public.stock_movements" in corpo
    assert "SET status = 'CANCELADA'" in corpo
    assert "INSERT INTO public.stock_movements" not in corpo


def test_us17_devolucao_grava_entrada_compensatoria():
    """Devolver preserva que a venda aconteceu: a saída original fica."""
    corpo = corpo_da_funcao("fn_return_sale")
    assert "INSERT INTO public.stock_movements" in corpo
    assert "'ENTRADA'" in corpo
    assert "'DEVOLUCAO_VENDA - venda '" in corpo
    assert "UPDATE public.stock_movements" not in corpo


@pytest.mark.parametrize("nome", ["fn_cancel_sale", "fn_return_sale"])
def test_us17_reversao_nunca_escreve_o_saldo_direto(nome):
    """Saldo é a soma das movimentações confirmadas; escrevê-lo direto seria
    sobrescrito pelo recálculo do trigger na movimentação seguinte."""
    corpo = corpo_da_funcao(nome)
    assert "UPDATE public.products" not in corpo


@pytest.mark.parametrize("nome", ["fn_cancel_sale", "fn_return_sale"])
def test_us17_reversao_esta_na_allowlist_de_execute(nome):
    politicas = (CODE / "policies" / "01_security.sql").read_text(encoding="utf-8")
    allowlist = politicas.split("v_names text[] := ARRAY[", 1)[1].split("];", 1)[0]
    assert f"'{nome}'" in allowlist
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_schema_declarativo.py -k "us17_reversao or us17_cancelamento or us17_devolucao" -q`
Expected: FAIL — `fn_cancel_sale não declarada em database/code`

- [ ] **Step 3: Escrever as duas funções**

Ao fim de `database/code/procedures/07_clients_sales.sql`:

```sql
-- Cancelamento de venda (US17).
--
-- A venda não deveria ter existido: as saídas dela passam a CANCELADA e o
-- trigger de recálculo devolve o saldo. É o mesmo contrato de
-- `fn_cancel_movement` — "cancelar uma confirmada devolve o saldo" — e a
-- guarda H13 aceita essa transição de propósito.
--
-- Nasce aqui, e não em `fn_cancel_movement`, porque aquela recusa cancelar
-- saída vinculada a venda: desfazer meia venda não é operação legítima.
CREATE OR REPLACE FUNCTION public.fn_cancel_sale(
    p_sale_id uuid,
    p_reason  text
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_status  public.sale_status;
    v_actor   uuid := public.fn_current_user_id();
    v_reason  text := btrim(COALESCE(p_reason, ''));
BEGIN
    SELECT s.company_id, s.status INTO v_company, v_status
      FROM public.sales s WHERE s.id = p_sale_id FOR UPDATE;

    -- Venda inexistente e venda de outra empresa dão a MESMA recusa: a
    -- diferença entre as duas diria ao chamador que o identificador existe.
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Venda não encontrada ou sem permissão para cancelar'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF v_reason = '' THEN
        RAISE EXCEPTION 'Informe o motivo do cancelamento'
            USING ERRCODE = 'check_violation';
    END IF;

    IF v_status <> 'CONCLUIDA' THEN
        RAISE EXCEPTION 'Somente venda concluída pode ser cancelada (situação atual: %)',
            v_status USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.sale_reversals (company_id, sale_id, kind, reason, created_by)
    VALUES (v_company, p_sale_id, 'CANCELAMENTO', v_reason, v_actor);

    UPDATE public.stock_movements
       SET status = 'CANCELADA'
     WHERE sale_id = p_sale_id AND status = 'CONFIRMADA';

    UPDATE public.sales SET status = 'CANCELADA' WHERE id = p_sale_id;

    RETURN jsonb_build_object('sale_id', p_sale_id, 'kind', 'CANCELAMENTO',
                              'reason', v_reason, 'status', 'CANCELADA');
END;
$$;

-- Devolução de venda (US17).
--
-- A venda ACONTECEU e a mercadoria voltou: a saída original continua
-- confirmada e uma ENTRADA compensatória por item devolve o saldo. Anular a
-- saída aqui apagaria do histórico de estoque que houve venda.
--
-- Devolução é sempre TOTAL nesta história. A parcial exigiria itens
-- devolvidos, recálculo do total efetivo e um estado intermediário.
CREATE OR REPLACE FUNCTION public.fn_return_sale(
    p_sale_id uuid,
    p_reason  text
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_status  public.sale_status;
    v_actor   uuid := public.fn_current_user_id();
    v_reason  text := btrim(COALESCE(p_reason, ''));
    v_item    RECORD;
BEGIN
    SELECT s.company_id, s.status INTO v_company, v_status
      FROM public.sales s WHERE s.id = p_sale_id FOR UPDATE;

    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Venda não encontrada ou sem permissão para devolver'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF v_reason = '' THEN
        RAISE EXCEPTION 'Informe o motivo da devolução'
            USING ERRCODE = 'check_violation';
    END IF;

    IF v_status <> 'CONCLUIDA' THEN
        RAISE EXCEPTION 'Somente venda concluída pode ser devolvida (situação atual: %)',
            v_status USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.sale_reversals (company_id, sale_id, kind, reason, created_by)
    VALUES (v_company, p_sale_id, 'DEVOLUCAO', v_reason, v_actor);

    FOR v_item IN
        SELECT i.product_id, i.quantity
          FROM public.sale_items i
         WHERE i.sale_id = p_sale_id AND i.product_id IS NOT NULL
         -- Mesma ordem de bloqueio da conclusão da venda, para que duas
         -- operações concorrentes sobre os mesmos produtos não se cruzem.
         ORDER BY i.product_id, i.id
    LOOP
        INSERT INTO public.stock_movements (
            company_id, product_id, sale_id, kind, quantity, status,
            note, created_by, confirmed_on
        ) VALUES (
            v_company, v_item.product_id, p_sale_id, 'ENTRADA',
            v_item.quantity, 'CONFIRMADA',
            'DEVOLUCAO_VENDA - venda ' || p_sale_id::text, v_actor, now()
        );
    END LOOP;

    UPDATE public.sales SET status = 'DEVOLVIDA' WHERE id = p_sale_id;

    RETURN jsonb_build_object('sale_id', p_sale_id, 'kind', 'DEVOLUCAO',
                              'reason', v_reason, 'status', 'DEVOLVIDA');
END;
$$;
```

- [ ] **Step 4: Allowlist, espelho e migration**

Em `database/code/policies/01_security.sql`, junto de `'fn_list_sales'`:

```sql
    'fn_cancel_sale', 'fn_return_sale',
```

Espelhar os dois arquivos para `database/supabase/schemas/` e replicar as duas funções na migration, com:

```sql
GRANT EXECUTE ON FUNCTION public.fn_cancel_sale(uuid, text) TO app_backend, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_return_sale(uuid, text) TO app_backend, authenticated;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_schema_declarativo.py tests/test_database_migrations.py -q`
Expected: PASS

- [ ] **Step 6: Commit (preparar e confirmar)**

Mensagem proposta: `feat(db): add sale cancellation and return with stock reversal`
**Parar e pedir confirmação.**

---

### Task 4: Enums de domínio e área de permissão

**Files:**
- Create: `src/stockflow/domain/enums/sale_status.py`
- Create: `src/stockflow/domain/enums/sale_reversal_kind.py`
- Modify: `src/stockflow/domain/permissions.py:106` (após a área `vendas`) e a seção de API derivada
- Test: `tests/unit/test_permission_matrix.py`

**Interfaces:**
- Consumes: `fn_cancel_sale` do banco (Task 3), lida como texto pelo teste de espelhamento.
- Produces: `SaleStatus` (`PENDENTE`, `CONCLUIDA`, `CANCELADA`, `DEVOLVIDA`, com `.label` e `.from_value`), `SaleReversalKind` (`CANCELAMENTO`, `DEVOLUCAO`, com `.label`), `can_reverse_sales(role_or_session) -> bool`, `ensure_can_reverse_sales(session, action="reverter vendas") -> None`.

- [ ] **Step 1: Write the failing test**

Acrescentar a `tests/unit/test_permission_matrix.py`:

```python
def test_us17_reverter_venda_e_so_do_admin():
    """Registrar venda é ADMIN+SELLER; desfazer é só do ADMIN.

    Quem vende não apaga o efeito da própria venda sem supervisão.
    """
    area = PERMISSION_MATRIX["vendas_reversao"]
    assert area.gravar == frozenset({ADMIN})
    assert PERMISSION_MATRIX["vendas"].gravar == frozenset({ADMIN, SELLER})


def test_us17_consultar_reversao_e_de_todos_os_papeis():
    assert PERMISSION_MATRIX["vendas_reversao"].ver == TODOS_OS_PAPEIS
```

E em `tests/unit/test_permission_matrix.py`, acrescentar a entrada ao mapa `POLICY_DE_LEITURA`:

```python
    "vendas_reversao": "sale_reversals_select",
```

Criar `tests/unit/test_sale_enums.py`:

```python
"""Os enums de venda espelham os tipos do banco."""

import pytest

from stockflow.domain.enums.sale_reversal_kind import SaleReversalKind
from stockflow.domain.enums.sale_status import SaleStatus


def test_status_cobre_os_quatro_rotulos_do_banco():
    assert {s.value for s in SaleStatus} == {
        "PENDENTE", "CONCLUIDA", "CANCELADA", "DEVOLVIDA"
    }


def test_status_revertido_identifica_cancelada_e_devolvida():
    assert SaleStatus.CANCELADA.revertida
    assert SaleStatus.DEVOLVIDA.revertida
    assert not SaleStatus.CONCLUIDA.revertida
    assert not SaleStatus.PENDENTE.revertida


def test_status_tem_rotulo_em_portugues():
    assert SaleStatus.DEVOLVIDA.label == "Devolvida"


def test_from_value_normaliza_texto_do_banco():
    assert SaleStatus.from_value(" concluida ") is SaleStatus.CONCLUIDA


def test_from_value_recusa_desconhecido():
    with pytest.raises(ValueError):
        SaleStatus.from_value("ESTORNADA")


def test_especie_de_reversao_tem_os_dois_valores_com_rotulo():
    assert {k.value for k in SaleReversalKind} == {"CANCELAMENTO", "DEVOLUCAO"}
    assert SaleReversalKind.DEVOLUCAO.label == "Devolução"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_sale_enums.py tests/unit/test_permission_matrix.py -q`
Expected: FAIL — `ModuleNotFoundError: stockflow.domain.enums.sale_status`

- [ ] **Step 3: Criar os enums**

`src/stockflow/domain/enums/sale_status.py`:

```python
"""Situação de uma venda, espelhando `public.sale_status`."""

from enum import StrEnum


class SaleStatus(StrEnum):
    """`CONCLUIDA` é o único estado reversível (US17).

    `PENDENTE` é carrinho em montagem; `CANCELADA` diz que a venda não
    deveria ter existido; `DEVOLVIDA` diz que existiu e a mercadoria voltou.
    As duas últimas são terminais: `sale_reversals` tem `UNIQUE (sale_id)`.
    """

    PENDENTE = "PENDENTE"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"
    DEVOLVIDA = "DEVOLVIDA"

    @property
    def label(self) -> str:
        return {SaleStatus.PENDENTE: "Pendente",
                SaleStatus.CONCLUIDA: "Concluída",
                SaleStatus.CANCELADA: "Cancelada",
                SaleStatus.DEVOLVIDA: "Devolvida"}[self]

    @property
    def revertida(self) -> bool:
        """Venda desfeita. Não entra em total de dinheiro vendido."""
        return self in (SaleStatus.CANCELADA, SaleStatus.DEVOLVIDA)

    @property
    def reversivel(self) -> bool:
        return self is SaleStatus.CONCLUIDA

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Situação de venda inválida: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Situação desconhecida: {value!r}") from None
```

`src/stockflow/domain/enums/sale_reversal_kind.py`:

```python
"""Espécie de reversão de venda, espelhando `public.sale_reversal_kind`."""

from enum import StrEnum


class SaleReversalKind(StrEnum):
    """Cancelar e devolver movem o estoque por mecanismos diferentes.

    `CANCELAMENTO` anula as saídas da venda; `DEVOLUCAO` grava entradas
    compensatórias e deixa a saída original de pé.
    """

    CANCELAMENTO = "CANCELAMENTO"
    DEVOLUCAO = "DEVOLUCAO"

    @property
    def label(self) -> str:
        return {SaleReversalKind.CANCELAMENTO: "Cancelamento",
                SaleReversalKind.DEVOLUCAO: "Devolução"}[self]

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Espécie de reversão inválida: {value!r}")
        try:
            return cls(value.strip().upper())
        except ValueError:
            raise ValueError(f"Espécie desconhecida: {value!r}") from None
```

- [ ] **Step 4: Declarar a área na matriz**

Em `src/stockflow/domain/permissions.py`, logo depois da área `"vendas"` (linha 106):

```python
    # Desfazer não é vender. Registrar venda segue ADMIN+SELLER; reverter é
    # só do ADMIN, para que quem vende não apague o efeito da própria venda
    # sem supervisão. `fonte_gravar` aponta a função que o banco usa para a
    # mesma decisão, e o teste de espelhamento compara as duas.
    "vendas_reversao": Area(
        ver=TODOS_OS_PAPEIS,
        gravar=_ADMIN,
        fonte_ver="sales_select",
        fonte_gravar="fn_cancel_sale",
    ),
```

E junto das demais funções derivadas (depois de `ensure_can_register_sales`):

```python
def can_reverse_sales(role_or_session) -> bool:
    return pode_gravar(role_or_session, "vendas_reversao")


def ensure_can_reverse_sales(session, action="cancelar ou devolver vendas") -> None:
    """Negação fechada: sessão ausente e papel sem alçada caem aqui."""
    exigir_gravar(session, "vendas_reversao", action)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_sale_enums.py tests/unit/test_permission_matrix.py -q`
Expected: PASS. `test_escrita_da_matriz_bate_com_o_sql[vendas_reversao]` prova que `_ADMIN` casa com o `ARRAY['ADMIN']` de `fn_cancel_sale`.

- [ ] **Step 6: Commit (preparar e confirmar)**

Mensagem proposta: `feat(domain): add sale status and reversal permission area`
**Parar e pedir confirmação.**

---

### Task 5: Porta, DTOs e serviço

**Files:**
- Create: `src/stockflow/application/ports/sale_repository.py`
- Create: `src/stockflow/application/dto/sale_filter.py`
- Modify: `src/stockflow/application/services/sale_service.py:132-133`
- Test: `tests/unit/test_sale_permissions.py`

**Interfaces:**
- Consumes: `ensure_can_reverse_sales`, `exigir_ver`, `SaleStatus` (Task 4).
- Produces: `SaleFilter(sale_id, date_from, date_to, client_id, seller_id, status, sort)`; `SalePage(rows, total, page, size)` com `.pages` e `.has_next`; `SaleRepository` com `list_page`, `get`, `cancel`, `revert`, `list_all`; `SaleService.list_sales(session, filtro=None, page=1, size=50)`, `.get_sale(session, sale_id)`, `.cancel_sale(session, sale_id, reason)`, `.return_sale(session, sale_id, reason)`.

- [ ] **Step 1: Write the failing test**

Criar `tests/unit/test_sale_permissions.py`:

```python
"""A guarda de permissão roda ANTES de tocar o repositório.

Padrão aprovado neste projeto: o fluxo negado não pode vazar informação nem
gastar consulta. O espião prova que o repositório não foi chamado.
"""

import pytest

from stockflow.application.dto.sale_filter import SaleFilter, SalePage
from stockflow.application.services.sale_service import SaleService
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.presentation.demo_accounts import conta_por_papel


class RepositorioEspiao:
    def __init__(self):
        self.chamadas = []

    def list_page(self, filtro, page, size):
        self.chamadas.append("list_page")
        return SalePage(rows=(), total=0, page=page, size=size)

    def get(self, sale_id):
        self.chamadas.append("get")
        return {}

    def cancel(self, sale_id, reason):
        self.chamadas.append("cancel")

    def revert(self, sale_id, reason):
        self.chamadas.append("revert")


def servico():
    repositorio = RepositorioEspiao()
    return SaleService(repositorio, clients=None, products=None), repositorio


def sessao(papel):
    return conta_por_papel(papel).session()


@pytest.mark.parametrize("papel", [UserRole.STOCK, UserRole.SELLER])
def test_reverter_sem_alcada_nao_toca_o_repositorio(papel):
    service, repositorio = servico()
    with pytest.raises(PermissionDeniedError):
        service.cancel_sale(sessao(papel), "venda-1", "engano")
    with pytest.raises(PermissionDeniedError):
        service.return_sale(sessao(papel), "venda-1", "cliente devolveu")
    assert repositorio.chamadas == []


def test_sessao_ausente_nao_reverte():
    service, repositorio = servico()
    with pytest.raises(PermissionDeniedError):
        service.cancel_sale(None, "venda-1", "engano")
    assert repositorio.chamadas == []


def test_admin_reverte():
    service, repositorio = servico()
    service.cancel_sale(sessao(UserRole.ADMIN), "venda-1", "engano")
    service.return_sale(sessao(UserRole.ADMIN), "venda-1", "devolvido")
    assert repositorio.chamadas == ["cancel", "revert"]


@pytest.mark.parametrize("motivo", ["", "   ", None])
def test_motivo_vazio_e_recusado_antes_do_repositorio(motivo):
    """Validação de domínio não gasta ida ao banco."""
    service, repositorio = servico()
    with pytest.raises(ValueError, match="motivo"):
        service.cancel_sale(sessao(UserRole.ADMIN), "venda-1", motivo)
    assert repositorio.chamadas == []


def test_consulta_exige_sessao_com_alcada_de_leitura():
    service, repositorio = servico()
    with pytest.raises(PermissionDeniedError):
        service.list_sales(None)
    assert repositorio.chamadas == []


@pytest.mark.parametrize("papel", [UserRole.ADMIN, UserRole.STOCK, UserRole.SELLER])
def test_os_tres_papeis_consultam_o_historico(papel):
    service, repositorio = servico()
    service.list_sales(sessao(papel))
    assert repositorio.chamadas == ["list_page"]


def test_filtro_vazio_e_o_padrao_e_nao_exige_construcao():
    service, repositorio = servico()
    pagina = service.list_sales(sessao(UserRole.ADMIN))
    assert isinstance(pagina, SalePage)


def test_pagina_calcula_quantas_paginas_existem():
    pagina = SalePage(rows=(), total=101, page=1, size=50)
    assert pagina.pages == 3
    assert pagina.has_next


def test_pagina_sem_linhas_tem_uma_pagina():
    assert SalePage(rows=(), total=0, page=1, size=50).pages == 1


def test_filtro_rejeita_tamanho_de_pagina_fora_do_limite():
    service, _ = servico()
    with pytest.raises(ValueError):
        service.list_sales(sessao(UserRole.ADMIN), size=0)
    with pytest.raises(ValueError):
        service.list_sales(sessao(UserRole.ADMIN), size=500)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_sale_permissions.py -q`
Expected: FAIL — `ModuleNotFoundError: stockflow.application.dto.sale_filter`

- [ ] **Step 3: Criar os DTOs**

`src/stockflow/application/dto/sale_filter.py`:

```python
"""Filtro e página do histórico de vendas (US17)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

#: Critérios aceitos por `fn_list_sales`. Lista fechada de propósito: texto
#: do chamador virando ORDER BY é injeção, e o banco recusa o que não estiver
#: aqui. Os rótulos são o que a tela mostra no combo.
ORDENACOES = (
    ("DATA_DESC", "Mais recentes primeiro"),
    ("DATA_ASC", "Mais antigas primeiro"),
    ("VALOR_DESC", "Maior valor"),
    ("VALOR_ASC", "Menor valor"),
    ("CLIENTE_ASC", "Cliente (A-Z)"),
)

TAMANHO_PADRAO = 50
TAMANHO_MAXIMO = 200


@dataclass(frozen=True)
class SaleFilter:
    """Todos os campos opcionais: filtro vazio lista tudo.

    `date_to` é inclusivo para quem usa a tela — o adaptador soma um dia
    antes de mandar ao banco, onde o limite é exclusivo. Sem isso, filtrar
    "até hoje" perderia as vendas de hoje.
    """

    sale_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    client_id: str | None = None
    seller_id: str | None = None
    status: str | None = None
    sort: str = "DATA_DESC"

    def __post_init__(self):
        validos = {codigo for codigo, _ in ORDENACOES}
        if self.sort not in validos:
            raise ValueError(f"Ordenação desconhecida: {self.sort!r}")
        if (self.date_from and self.date_to
                and self.date_from > self.date_to):
            raise ValueError("A data inicial não pode ser depois da final.")

    def com(self, **campos) -> "SaleFilter":
        """Cópia com campos trocados, para a tela não remontar o filtro."""
        return replace(self, **campos)

    @property
    def ativo(self) -> bool:
        return any((self.sale_id, self.date_from, self.date_to,
                    self.client_id, self.seller_id, self.status))


@dataclass(frozen=True)
class SalePage:
    """Uma página e o total que casa com o filtro.

    `total` vem da MESMA leitura que trouxe as linhas (`count(*) OVER ()`):
    uma segunda contagem poderia divergir sob concorrência, e a tela
    mostraria um número de páginas que não corresponde ao que lista.
    """

    rows: tuple
    total: int
    page: int
    size: int

    @property
    def pages(self) -> int:
        if self.size <= 0:
            return 1
        return max(1, -(-self.total // self.size))

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1
```

- [ ] **Step 4: Criar a porta**

`src/stockflow/application/ports/sale_repository.py`:

```python
"""Porta de persistência de vendas.

Vendas era o único domínio sem porta declarada: enquanto o contrato era
"grava e lista tudo", os dois adaptadores cabiam na cabeça. Com consulta
paginada, filtros e reversão, o contrato precisa estar escrito num lugar só
— senão o repositório de demonstração e o do Supabase divergem em silêncio,
e os testes de interface passam a validar ficção.
"""

from typing import Protocol

from stockflow.application.dto.sale_filter import SaleFilter, SalePage


class SaleRepository(Protocol):
    def list_page(self, filtro: SaleFilter, page: int, size: int) -> SalePage:
        """Uma página do histórico e o total que casa com o filtro.

        A ordem é a de `filtro.sort`, sempre desempatada pelo identificador:
        sem desempate a página seguinte repete ou pula linha.
        """
        ...

    def get(self, sale_id: str) -> dict | None:
        """Uma venda com itens e vínculo de reversão, ou `None`."""
        ...

    def cancel(self, sale_id: str, reason: str) -> dict:
        """Anula a venda e devolve o saldo. Só para venda concluída."""
        ...

    def revert(self, sale_id: str, reason: str) -> dict:
        """Devolve a venda: entrada compensatória, saída original de pé."""
        ...

    def list_all(self) -> list:
        """Todo o histórico, sem paginar.

        Continua existindo para Dashboard e Relatórios, que agregam em vez
        de listar. Não usar em tela de consulta: `max_rows` do PostgREST
        corta em 1000 linhas sem avisar.
        """
        ...
```

- [ ] **Step 5: Reescrever a parte de consulta e reversão do serviço**

Em `src/stockflow/application/services/sale_service.py`, substituir `list_sales` (linhas 132-133) por:

```python
    def list_sales(self, session, filtro=None, page=1, size=TAMANHO_PADRAO):
        """Página do histórico, com a alçada conferida antes da consulta.

        Antes da US17 este método não recebia sessão: a RLS escopava por
        empresa e o resultado ficava certo por consequência, não por
        decisão. A guarda explícita alinha vendas às demais áreas.
        """
        exigir_ver(session, "vendas", "consultar o histórico de vendas")
        if not isinstance(page, int) or page < 1:
            raise ValueError("Página inválida.")
        if not isinstance(size, int) or not (1 <= size <= TAMANHO_MAXIMO):
            raise ValueError(
                f"Tamanho de página inválido: use entre 1 e {TAMANHO_MAXIMO}."
            )
        return self.repository.list_page(filtro or SaleFilter(), page, size)

    def get_sale(self, session, sale_id):
        exigir_ver(session, "vendas", "consultar o histórico de vendas")
        if not sale_id:
            raise ValueError("Não foi possível identificar a venda.")
        return self.repository.get(sale_id)

    def cancel_sale(self, session, sale_id, reason):
        """Anula a venda. Alçada e motivo conferidos antes do repositório."""
        ensure_can_reverse_sales(session, action="cancelar vendas")
        return self.repository.cancel(sale_id, self._motivo(reason))

    def return_sale(self, session, sale_id, reason):
        ensure_can_reverse_sales(session, action="devolver vendas")
        return self.repository.revert(sale_id, self._motivo(reason))

    @staticmethod
    def _motivo(reason) -> str:
        """O motivo é obrigatório e nasce aqui, não na tela.

        O banco recusa vazio também, mas deixar a recusa só lá gastaria uma
        ida à rede para dizer o que a aplicação já sabia.
        """
        texto = (reason or "").strip()
        if not texto:
            raise ValueError("Informe o motivo da operação.")
        if len(texto) > 300:
            raise ValueError("O motivo deve ter no máximo 300 caracteres.")
        return texto
```

Acrescentar aos imports do arquivo:

```python
from stockflow.application.dto.sale_filter import (
    TAMANHO_MAXIMO,
    TAMANHO_PADRAO,
    SaleFilter,
)
from stockflow.domain.permissions import (
    ensure_can_register_sales,
    ensure_can_reverse_sales,
    exigir_ver,
)
```

(substituindo o import existente de `ensure_can_register_sales`).

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_sale_permissions.py -q`
Expected: PASS

- [ ] **Step 7: Verificar o estrago nos chamadores**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: FAIL em `tests/test_vendas_clientes.py` e vizinhos — `list_sales()` perdeu a assinatura sem argumento. **Isso é esperado**: os chamadores são consertados na Task 6 e na Task 7. Anotar quais falharam antes de seguir.

- [ ] **Step 8: Commit (preparar e confirmar)**

Mensagem proposta: `feat(application): add sale repository port, filters and reversal service`
**Parar e pedir confirmação.**

---

### Task 6: Adaptadores — demonstração e Supabase

**Files:**
- Modify: `src/stockflow/infrastructure/repositories/demo_sale_repository.py:90-92`
- Modify: `src/stockflow/infrastructure/repositories/supabase_sale_repository.py:30-43`
- Test: `tests/unit/test_sale_repositories.py`

**Interfaces:**
- Consumes: `SaleFilter`, `SalePage` (Task 5).
- Produces: nos dois repositórios, `list_page(filtro, page, size) -> SalePage`, `get(sale_id) -> dict | None`, `cancel(sale_id, reason) -> dict`, `revert(sale_id, reason) -> dict`. A linha de venda ganha as chaves `status`, `seller`, `reversal_kind`, `reversal_reason`, `reversal_on`, `reversal_by`, preservando as chaves que Dashboard e Relatórios já leem (`id`, `cliente`, `produto`, `valor`, `data`, `total`, `itens_count`).

- [ ] **Step 1: Write the failing test**

Criar `tests/unit/test_sale_repositories.py`:

```python
"""Os dois adaptadores satisfazem a MESMA semântica.

Se o de demonstração mentir sobre filtro, ordem ou paginação, os testes de
interface validam ficção: a tela passa verde contra um comportamento que o
banco não tem.
"""

from datetime import date
from decimal import Decimal

import pytest

from stockflow.application.dto.sale_filter import SaleFilter
from stockflow.infrastructure.repositories.demo_sale_repository import (
    DemoSaleRepository,
)


@pytest.fixture
def repositorio():
    repo = DemoSaleRepository()
    repo.rows = [
        dict(id=f"VND-{i:04d}", cliente=f"Cliente {i % 5}", produto="Produto",
             valor="R$ 10,00", data=f"2026-10-{(i % 28) + 1:02d} 10:00",
             total="10.00", itens_count=1, status="CONCLUIDA",
             seller="Vendedor", seller_id="s1", client_id=f"c{i % 5}",
             payment_method="PIX", discount="0", items=[])
        for i in range(120)
    ]
    return repo


def test_pagina_devolve_o_tamanho_pedido_e_o_total_filtrado(repositorio):
    pagina = repositorio.list_page(SaleFilter(), page=1, size=50)
    assert len(pagina.rows) == 50
    assert pagina.total == 120
    assert pagina.pages == 3


def test_paginacao_nao_repete_nem_pula_registro(repositorio):
    vistos = []
    for numero in (1, 2, 3):
        vistos += [linha["id"] for linha in
                   repositorio.list_page(SaleFilter(), numero, 50).rows]
    assert len(vistos) == 120
    assert len(set(vistos)) == 120


def test_pagina_alem_do_fim_vem_vazia_sem_estourar(repositorio):
    assert repositorio.list_page(SaleFilter(), page=99, size=50).rows == ()


def test_filtro_por_cliente_muda_o_total(repositorio):
    pagina = repositorio.list_page(SaleFilter(client_id="c1"), 1, 50)
    assert pagina.total == 24
    assert all(linha["client_id"] == "c1" for linha in pagina.rows)


def test_filtros_combinam(repositorio):
    repositorio.rows[0]["status"] = "CANCELADA"
    repositorio.rows[0]["client_id"] = "c0"
    pagina = repositorio.list_page(
        SaleFilter(client_id="c0", status="CANCELADA"), 1, 50
    )
    assert pagina.total == 1


def test_filtro_por_id_casa_por_prefixo(repositorio):
    pagina = repositorio.list_page(SaleFilter(sale_id="VND-0001"), 1, 50)
    assert [linha["id"] for linha in pagina.rows] == ["VND-0001"]


def test_filtro_de_periodo_inclui_o_ultimo_dia(repositorio):
    pagina = repositorio.list_page(
        SaleFilter(date_from=date(2026, 10, 5), date_to=date(2026, 10, 5)), 1, 50
    )
    assert pagina.total > 0
    assert all("2026-10-05" in linha["data"] for linha in pagina.rows)


def test_ordenacao_por_valor_decrescente(repositorio):
    repositorio.rows[7]["total"] = "999.00"
    pagina = repositorio.list_page(SaleFilter(sort="VALOR_DESC"), 1, 5)
    assert pagina.rows[0]["total"] == "999.00"


def test_cancelar_marca_a_venda_e_devolve_o_saldo():
    repo = DemoSaleRepository()
    antes = int(repo._products["PRD-009"].stock)
    venda = repo.register_multiple(
        type("C", (), {"name": "Ana", "client_id": "c1"})(),
        (__import__("stockflow.application.dto.sale_item", fromlist=["SaleItemInput"])
         .SaleItemInput("PRD-009", 2),),
        Decimal("20.00"),
    )
    assert int(repo._products["PRD-009"].stock) == antes - 2
    repo.cancel(venda["id"], "registro em duplicidade")
    assert repo.get(venda["id"])["status"] == "CANCELADA"
    assert int(repo._products["PRD-009"].stock) == antes


def test_venda_revertida_nao_reverte_de_novo():
    repo = DemoSaleRepository()
    venda = repo.register_multiple(
        type("C", (), {"name": "Ana", "client_id": "c1"})(),
        (__import__("stockflow.application.dto.sale_item", fromlist=["SaleItemInput"])
         .SaleItemInput("PRD-009", 1),),
        Decimal("10.00"),
    )
    repo.cancel(venda["id"], "engano")
    with pytest.raises(ValueError, match="já foi"):
        repo.revert(venda["id"], "tentativa dupla")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_sale_repositories.py -q`
Expected: FAIL — `AttributeError: 'DemoSaleRepository' object has no attribute 'list_page'`

- [ ] **Step 3: Implementar no repositório de demonstração**

Acrescentar a `demo_sale_repository.py` um módulo auxiliar de filtragem, usado só por ele:

```python
def _data_da_linha(linha):
    """A linha guarda a data já formatada para a tela; o filtro precisa de
    `date`. Aceita os dois formatos que `sale_row` produz."""
    texto = str(linha.get("data", ""))[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


_CHAVE_DE_ORDEM = {
    "DATA_DESC": (lambda l: (_data_da_linha(l) or date.min, l["id"]), True),
    "DATA_ASC": (lambda l: (_data_da_linha(l) or date.min, l["id"]), False),
    "VALOR_DESC": (lambda l: (Decimal(l["total"]), l["id"]), True),
    "VALOR_ASC": (lambda l: (Decimal(l["total"]), l["id"]), False),
    "CLIENTE_ASC": (lambda l: (str(l["cliente"]).casefold(), l["id"]), False),
}
```

E os métodos na classe:

```python
    def _combina(self, linha, filtro):
        if filtro.sale_id and not str(linha["id"]).lower().startswith(
            filtro.sale_id.strip().lower()
        ):
            return False
        if filtro.client_id and linha.get("client_id") != filtro.client_id:
            return False
        if filtro.seller_id and linha.get("seller_id") != filtro.seller_id:
            return False
        if filtro.status and linha.get("status", "CONCLUIDA") != filtro.status:
            return False
        quando = _data_da_linha(linha)
        if filtro.date_from and (quando is None or quando < filtro.date_from):
            return False
        # Inclusivo na tela: "até dia 5" inclui o dia 5 inteiro.
        if filtro.date_to and (quando is None or quando > filtro.date_to):
            return False
        return True

    def list_page(self, filtro, page, size):
        from stockflow.application.dto.sale_filter import SalePage

        with self._lock:
            linhas = [l for l in self.rows if self._combina(l, filtro)]
        chave, reverso = _CHAVE_DE_ORDEM[filtro.sort]
        linhas.sort(key=chave, reverse=reverso)
        inicio = (page - 1) * size
        return SalePage(rows=tuple(linhas[inicio:inicio + size]),
                        total=len(linhas), page=page, size=size)

    def get(self, sale_id):
        with self._lock:
            return next((dict(l) for l in self.rows if l["id"] == str(sale_id)), None)

    def cancel(self, sale_id, reason):
        return self._reverter(sale_id, reason, "CANCELAMENTO", "CANCELADA")

    def revert(self, sale_id, reason):
        return self._reverter(sale_id, reason, "DEVOLUCAO", "DEVOLVIDA")

    def _reverter(self, sale_id, reason, kind, status):
        """Devolve o saldo pelo repositório de movimentação, nunca escrevendo
        `Product.stock` direto — o mesmo contrato do banco."""
        with self._lock:
            linha = next((l for l in self.rows if l["id"] == str(sale_id)), None)
            if linha is None:
                raise ValueError("Venda não encontrada.")
            if linha.get("status", "CONCLUIDA") != "CONCLUIDA":
                raise ValueError(
                    f"Esta venda já foi {linha['status'].lower()}."
                )
            self.movements.reverse_sale(sale_id, linha.get("items", []))
            linha.update(status=status, reversal_kind=kind,
                         reversal_reason=reason,
                         reversal_on=datetime.now().strftime("%d/%m/%Y %H:%M"),
                         reversal_by="Demonstração")
            return dict(linha)
```

Acrescentar os imports `from datetime import date, datetime`.

Em `demo_movement_repository.py`, acrescentar `reverse_sale(sale_id, items)`: devolve ao catálogo a quantidade de cada item e registra a movimentação de volta, sob o mesmo lock que `register_sale` usa. Reaproveitar o caminho interno que `register_sale` já usa para mexer no saldo, invertendo o sentido.

- [ ] **Step 4: Implementar no repositório do Supabase**

Em `supabase_sale_repository.py`:

```python
    def list_page(self, filtro, page, size):
        from stockflow.application.dto.sale_filter import SalePage

        # O banco usa limite superior EXCLUSIVO; a tela pensa inclusivo.
        # A conversão mora aqui, e não na tela, para que o repositório de
        # demonstração e este concordem sobre o que "até dia 5" significa.
        ate = filtro.date_to + timedelta(days=1) if filtro.date_to else None
        linhas = self._client.rpc("fn_list_sales", {
            "p_company_id": self._company_id,
            "p_sale_id": filtro.sale_id or None,
            "p_from": filtro.date_from.isoformat() if filtro.date_from else None,
            "p_to": ate.isoformat() if ate else None,
            "p_client_id": filtro.client_id or None,
            "p_seller_id": filtro.seller_id or None,
            "p_status": filtro.status or None,
            "p_sort": filtro.sort,
            "p_limit": size,
            "p_offset": (page - 1) * size,
        }).execute().data or []
        total = int(linhas[0]["total_count"]) if linhas else 0
        return SalePage(rows=tuple(_history_row(l) for l in linhas),
                        total=total, page=page, size=size)

    def get(self, sale_id):
        pagina = self.list_page(SaleFilter(sale_id=str(sale_id)), 1, 1)
        return pagina.rows[0] if pagina.rows else None

    def cancel(self, sale_id, reason):
        return self._client.rpc("fn_cancel_sale", {
            "p_sale_id": str(sale_id), "p_reason": reason,
        }).execute().data

    def revert(self, sale_id, reason):
        return self._client.rpc("fn_return_sale", {
            "p_sale_id": str(sale_id), "p_reason": reason,
        }).execute().data
```

E `_history_row(linha)`, irmã de `_receipt_row`, que monta a linha da tela a partir do retorno de `fn_list_sales`, reaproveitando `sale_row` e `resumo_dos_itens` e acrescentando `status`, `seller`, `seller_id`, `client_id`, `reversal_kind`, `reversal_reason`, `reversal_on`, `reversal_by`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_sale_repositories.py tests/test_sales_checkout_regression.py -q`
Expected: PASS

- [ ] **Step 6: Commit (preparar e confirmar)**

Mensagem proposta: `feat(infra): add paginated query and reversal to sale repositories`
**Parar e pedir confirmação.**

---

### Task 7: Filtros, ordenação e paginação na tela de Vendas

**Files:**
- Modify: `src/stockflow/presentation/pages/vendas.py:311-360` (card do histórico), `:371-440` (carga), `:773-806` (desenho e filtro)
- Test: `tests/test_us17_historico_de_vendas.py`

**Interfaces:**
- Consumes: `SaleService.list_sales`, `SaleFilter`, `ORDENACOES`, `SaleStatus`.
- Produces: em `VendasPage` — `filtro_id`, `filtro_inicio`, `filtro_fim`, `filtro_cliente`, `filtro_vendedor`, `filtro_status`, `ordenacao_combo`, `limpar_filtros_button`, `anterior_button`, `proximo_button`, `paginacao_label`, `detalhes_requested = Signal(str)`, e os métodos `filtro_atual() -> SaleFilter`, `ir_para_pagina(numero)`, `limpar_filtros()`.

- [ ] **Step 1: Write the failing test**

Criar `tests/test_us17_historico_de_vendas.py` com, no mínimo, estes casos — cada um exercitando o caminho do usuário, não o interno:

```python
"""Consulta do histórico de vendas pela tela (US17)."""

from datetime import date, timedelta

import pytest

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.pages.vendas import VendasPage


@pytest.fixture
def pagina(qapp):
    page = VendasPage(session=conta_por_papel(UserRole.ADMIN).session())
    page.service.repository.rows = [
        dict(id=f"VND-{i:04d}", cliente=f"Cliente {i % 4}", produto="Produto",
             valor="R$ 10,00", data=f"{(i % 28) + 1:02d}/10/2026 10:00",
             total=f"{10 + i}.00", itens_count=1,
             status="CANCELADA" if i == 3 else "CONCLUIDA",
             seller="Vendedor", seller_id="s1", client_id=f"c{i % 4}",
             payment_method="PIX", discount="0", items=[])
        for i in range(120)
    ]
    page.reload_sales()
    yield page
    page.close()


def test_historico_mostra_uma_pagina_e_nao_tudo(pagina):
    assert pagina.table.rowCount() == 50
    assert "1" in pagina.paginacao_label.text()


def test_avancar_e_voltar_pagina_nao_repete_registro(pagina):
    primeira = [pagina.table.item(r, 0).text() for r in range(pagina.table.rowCount())]
    pagina.proximo_button.click()
    segunda = [pagina.table.item(r, 0).text() for r in range(pagina.table.rowCount())]
    assert not set(primeira) & set(segunda)
    pagina.anterior_button.click()
    assert [pagina.table.item(r, 0).text()
            for r in range(pagina.table.rowCount())] == primeira


def test_primeira_pagina_desabilita_anterior(pagina):
    assert not pagina.anterior_button.isEnabled()
    assert pagina.proximo_button.isEnabled()


def test_filtro_por_cliente_muda_a_lista_e_o_total(pagina):
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c1"))
    assert pagina.table.rowCount() == 30
    assert "30" in pagina.result_count.text()


def test_filtro_por_status_encontra_a_cancelada(pagina):
    pagina.filtro_status.setCurrentIndex(pagina.filtro_status.findData("CANCELADA"))
    assert pagina.table.rowCount() == 1


def test_filtros_combinam(pagina):
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c3"))
    pagina.filtro_status.setCurrentIndex(pagina.filtro_status.findData("CANCELADA"))
    assert pagina.table.rowCount() == 1


def test_filtro_por_id_casa_por_prefixo(pagina):
    pagina.filtro_id.setText("VND-0007")
    assert pagina.table.rowCount() == 1


def test_filtro_sobrevive_a_paginacao(pagina):
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c1"))
    pagina.proximo_button.click()
    assert pagina.filtro_atual().client_id == "c1"
    assert all(pagina.table.item(r, 1).text() == "Cliente 1"
               for r in range(pagina.table.rowCount()))


def test_mudar_filtro_volta_para_a_primeira_pagina(pagina):
    pagina.proximo_button.click()
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c2"))
    assert not pagina.anterior_button.isEnabled()


def test_filtro_sobrevive_a_recarga(pagina):
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c1"))
    pagina.reload_sales()
    assert pagina.filtro_atual().client_id == "c1"


def test_limpar_filtros_restaura_a_lista_inteira(pagina):
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c1"))
    pagina.limpar_filtros_button.click()
    assert pagina.table.rowCount() == 50
    assert not pagina.filtro_atual().ativo


def test_ordenar_por_maior_valor(pagina):
    pagina.ordenacao_combo.setCurrentIndex(
        pagina.ordenacao_combo.findData("VALOR_DESC")
    )
    assert pagina.table.item(0, 0).text() == "VND-0119"


def test_coluna_de_status_distingue_cancelada(pagina):
    pagina.filtro_status.setCurrentIndex(pagina.filtro_status.findData("CANCELADA"))
    cabecalhos = [pagina.table.horizontalHeaderItem(c).text()
                  for c in range(pagina.table.columnCount())]
    assert "Status" in cabecalhos
    coluna = cabecalhos.index("Status")
    assert pagina.table.item(0, coluna).text() == "Cancelada"


def test_filtro_de_periodo_inclui_o_ultimo_dia(pagina):
    pagina.filtro_inicio.setDate(pagina.filtro_inicio.date().fromString("05/10/2026", "dd/MM/yyyy"))
    pagina.filtro_fim.setDate(pagina.filtro_fim.date().fromString("05/10/2026", "dd/MM/yyyy"))
    assert pagina.table.rowCount() > 0


def test_historico_vazio_explica_o_vazio(pagina):
    pagina.filtro_id.setText("NAO-EXISTE")
    assert pagina.table.rowCount() == 0
    assert "Nenhuma venda encontrada" in pagina.empty_label.text()


def test_tabela_continua_sem_permitir_edicao(pagina):
    from PySide6.QtWidgets import QAbstractItemView
    assert pagina.table.editTriggers() == QAbstractItemView.NoEditTriggers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_us17_historico_de_vendas.py -q`
Expected: FAIL — `AttributeError: 'VendasPage' object has no attribute 'paginacao_label'`

- [ ] **Step 3: Construir a linha de filtros**

No card do histórico de `vendas.py`, depois do `search_input` e antes da tabela, acrescentar o método `_criar_filtros_do_historico()` que monta e devolve o layout com:

- `self.filtro_id = _line_edit("ID da venda")`, com `textChanged` ligado a `self._filtro_mudou`
- `self.filtro_inicio` e `self.filtro_fim` (`QDateEdit`, `setCalendarPopup(True)`, formato `dd/MM/yyyy`), cada um com `dateChanged` ligado a `_filtro_mudou`; acompanhados dos presets de 7 e 30 dias, no mesmo molde de `movimentacoes.py`
- `self.filtro_cliente` (`QComboBox`) preenchido por `recarregar_clientes_disponiveis`, com o item zero "Todos os clientes" e `userData=None`
- `self.filtro_vendedor` (`QComboBox`) preenchido a partir dos vendedores presentes na página atual, item zero "Todos os vendedores"
- `self.filtro_status` (`QComboBox`) com "Todos os status" mais um item por `SaleStatus`, `userData` igual ao `value`
- `self.ordenacao_combo` (`QComboBox`) alimentado por `ORDENACOES`
- `self.limpar_filtros_button`, ligado a `self.limpar_filtros`

E a paginação, reaproveitando o visual de `movimentacoes._create_pagination_controls`:

```python
    def _criar_controles_de_pagina(self):
        layout = QHBoxLayout()
        layout.setSpacing(8)
        self.anterior_button = QPushButton("‹ Anterior")
        self.anterior_button.setAccessibleName("Página anterior de vendas")
        self.anterior_button.clicked.connect(
            lambda: self.ir_para_pagina(self._pagina_atual - 1)
        )
        self.paginacao_label = QLabel()
        self.paginacao_label.setAlignment(Qt.AlignCenter)
        self.paginacao_label.setAccessibleName("Informação de paginação de vendas")
        self.proximo_button = QPushButton("Próximo ›")
        self.proximo_button.setAccessibleName("Próxima página de vendas")
        self.proximo_button.clicked.connect(
            lambda: self.ir_para_pagina(self._pagina_atual + 1)
        )
        for widget in (self.anterior_button, self.paginacao_label, self.proximo_button):
            widget.setFixedHeight(32)
            layout.addWidget(widget)
        layout.addStretch()
        return layout
```

- [ ] **Step 4: Trocar a carga por consulta paginada**

```python
    def filtro_atual(self) -> SaleFilter:
        """Lê os widgets e monta o filtro. Fonte única do que está filtrado.

        A tela não guarda uma cópia do filtro: guardar os dois leva a eles
        divergirem, que foi como a busca já sobreviveu a uma recarga
        mostrando resultado de outro termo.
        """
        return SaleFilter(
            sale_id=self.filtro_id.text().strip() or None,
            date_from=self.filtro_inicio.date().toPython()
                      if self.filtro_periodo_ativo else None,
            date_to=self.filtro_fim.date().toPython()
                    if self.filtro_periodo_ativo else None,
            client_id=self.filtro_cliente.currentData(),
            seller_id=self.filtro_vendedor.currentData(),
            status=self.filtro_status.currentData(),
            sort=self.ordenacao_combo.currentData() or "DATA_DESC",
        )

    def _filtro_mudou(self, *_):
        """Toda mudança de filtro volta para a página 1.

        Ficar na página 5 de um filtro novo mostra uma tela vazia que parece
        "não há vendas", quando o que houve foi deslocamento sem resultado.
        """
        self.ir_para_pagina(1)

    def ir_para_pagina(self, numero):
        if self._loading or numero < 1:
            return
        self._pagina_atual = numero
        self.reload_sales()

    def limpar_filtros(self):
        for widget in (self.filtro_id,):
            widget.clear()
        for combo in (self.filtro_cliente, self.filtro_vendedor, self.filtro_status):
            combo.setCurrentIndex(0)
        self.ordenacao_combo.setCurrentIndex(0)
        self.filtro_periodo_ativo = False
        self.ir_para_pagina(1)
```

`reload_sales` passa a chamar `self.service.list_sales(self.session, self.filtro_atual(), self._pagina_atual, PAGE_SIZE)` pelo worker, e o callback de sucesso guarda `self.historico_vendas = list(pagina.rows)` e `self._pagina = pagina` antes de redesenhar.

`_carregar_dados` acompanha a mesma mudança.

- [ ] **Step 5: Coluna de status e contagem**

`setColumnCount(6)` e cabeçalhos `["ID Venda", "Cliente Associado", "Produto", "Valor Total", "Data", "Status"]`. Em `atualizar_tabela_historico`, preencher a sexta coluna com `SaleStatus.from_value(venda.get("status", "CONCLUIDA")).label` e pintar o chip com o mapa de cores no molde de `movimentacoes.py:52`:

```python
CORES_DE_STATUS = {
    SaleStatus.CONCLUIDA.label: ("#166534", "#DCFCE7"),
    SaleStatus.CANCELADA.label: ("#8A3B3B", "#FBE9E9"),
    SaleStatus.DEVOLVIDA.label: ("#92400E", "#FEF3C7"),
    SaleStatus.PENDENTE.label: ("#334155", "#E2E8F0"),
}
```

`_atualizar_paginacao` escreve `f"Página {p} de {total_de_paginas}"`, habilita e desabilita os dois botões, e `result_count` passa a mostrar `f"{len(rows)} de {pagina.total} vendas"`.

A caixa de busca livre que já existe **permanece**, filtrando a página carregada — é o único filtro instantâneo e os usuários já a conhecem. O rótulo muda para "Buscar nesta página…", para que ninguém a confunda com os filtros que consultam o banco.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_us17_historico_de_vendas.py tests/test_vendas_clientes.py tests/test_operations_filters.py -q`
Expected: PASS. Ajustar `test_vendas_clientes.py` e `test_operations_filters.py` onde eles assumem a assinatura antiga de `list_sales`.

- [ ] **Step 7: Commit (preparar e confirmar)**

Mensagem proposta: `feat(ui): add filters, sorting and pagination to sales history`
**Parar e pedir confirmação.**

---

### Task 8: Tela de detalhe da venda

**Files:**
- Create: `src/stockflow/presentation/pages/sale_details.py`
- Modify: `src/stockflow/presentation/pages/vendas.py` (botão de detalhe por linha)
- Modify: `src/stockflow/presentation/windows/main_window.py:179, 267, 287-289, 770-779`
- Test: `tests/test_us17_detalhe_da_venda.py`

**Interfaces:**
- Consumes: `SaleService.get_sale`, `SaleStatus`, `SaleReversalKind`.
- Produces: `SaleDetailsPage` com `load_sale(venda)`, `back_button`, `cancel_button`, `return_button`, `cancel_requested = Signal(str, str)`, `return_requested = Signal(str, str)`; em `VendasPage`, `detalhes_requested = Signal(str)`.

- [ ] **Step 1: Write the failing test**

Criar `tests/test_us17_detalhe_da_venda.py`:

```python
"""Tela de detalhe da venda (US17/SCRUM-221)."""

import pytest

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.pages.sale_details import SaleDetailsPage

VENDA = {
    "id": "VND-0001", "cliente": "Ana Ferreira", "seller": "João Vendedor",
    "data": "05/10/2026 14:30", "status": "CONCLUIDA",
    "payment_method": "PIX", "discount": "5.00", "total": "115.00",
    "valor": "R$ 115,00",
    "items": [
        {"product_code": "PRD-001", "product_name": "Teclado",
         "quantity": 2, "unit_price": "30.00", "subtotal": "60.00"},
        {"product_code": "PRD-002", "product_name": "Mouse",
         "quantity": 2, "unit_price": "30.00", "subtotal": "60.00"},
    ],
}

REVERTIDA = VENDA | {
    "status": "DEVOLVIDA", "reversal_kind": "DEVOLUCAO",
    "reversal_reason": "Cliente desistiu da compra",
    "reversal_on": "06/10/2026 09:00", "reversal_by": "Maria Admin",
}


@pytest.fixture
def pagina(qapp):
    page = SaleDetailsPage()
    yield page
    page.close()


def test_detalhe_mostra_cliente_vendedor_e_pagamento(pagina):
    pagina.load_sale(VENDA, conta_por_papel(UserRole.ADMIN).session())
    texto = pagina.resumo_text()
    assert "Ana Ferreira" in texto
    assert "João Vendedor" in texto
    assert "PIX" in texto


def test_detalhe_lista_itens_com_preco_unitario_e_subtotal(pagina):
    pagina.load_sale(VENDA, conta_por_papel(UserRole.ADMIN).session())
    assert pagina.itens_table.rowCount() == 2
    cabecalhos = [pagina.itens_table.horizontalHeaderItem(c).text()
                  for c in range(pagina.itens_table.columnCount())]
    assert "Preço unitário" in cabecalhos
    assert "Subtotal" in cabecalhos


def test_detalhe_mostra_desconto_e_total(pagina):
    pagina.load_sale(VENDA, conta_por_papel(UserRole.ADMIN).session())
    assert "5,00" in pagina.totais_label.text()
    assert "115,00" in pagina.totais_label.text()


def test_venda_revertida_mostra_motivo_autor_e_data(pagina):
    pagina.load_sale(REVERTIDA, conta_por_papel(UserRole.ADMIN).session())
    assert pagina.reversao_card.isVisible()
    texto = pagina.reversao_label.text()
    assert "Devolução" in texto
    assert "Cliente desistiu da compra" in texto
    assert "Maria Admin" in texto
    assert "06/10/2026" in texto


def test_venda_sem_reversao_esconde_o_bloco(pagina):
    pagina.load_sale(VENDA, conta_por_papel(UserRole.ADMIN).session())
    assert not pagina.reversao_card.isVisible()


def test_admin_ve_as_acoes_em_venda_concluida(pagina):
    pagina.load_sale(VENDA, conta_por_papel(UserRole.ADMIN).session())
    assert pagina.cancel_button.isEnabled()
    assert pagina.return_button.isEnabled()


@pytest.mark.parametrize("papel", [UserRole.SELLER, UserRole.STOCK])
def test_quem_nao_e_admin_nao_reverte(pagina, papel):
    pagina.load_sale(VENDA, conta_por_papel(papel).session())
    assert not pagina.cancel_button.isEnabled()
    assert not pagina.return_button.isEnabled()


def test_venda_ja_revertida_nao_oferece_acao_nem_para_admin(pagina):
    pagina.load_sale(REVERTIDA, conta_por_papel(UserRole.ADMIN).session())
    assert not pagina.cancel_button.isEnabled()
    assert not pagina.return_button.isEnabled()


def test_detalhe_nao_permite_editar_os_itens(pagina):
    from PySide6.QtWidgets import QAbstractItemView
    pagina.load_sale(VENDA, conta_por_papel(UserRole.ADMIN).session())
    assert pagina.itens_table.editTriggers() == QAbstractItemView.NoEditTriggers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_us17_detalhe_da_venda.py -q`
Expected: FAIL — `ModuleNotFoundError: stockflow.presentation.pages.sale_details`

- [ ] **Step 3: Criar a página**

`src/stockflow/presentation/pages/sale_details.py`, no molde de `product_details.py` e `movement_details.py`: cabeçalho com `back_button`, cartão de resumo, `itens_table` com cinco colunas (`Código`, `Produto`, `Qtd.`, `Preço unitário`, `Subtotal`) e `NoEditTriggers`, `totais_label`, `reversao_card` escondido por padrão, e a linha de ações.

A regra de habilitação das ações mora num método só:

```python
    def _aplicar_alcada(self, venda, session):
        """Botão desabilitado é cortesia visual; a decisão é do domínio.

        A recusa real acontece no serviço e de novo no banco. Isto aqui só
        evita oferecer ao usuário uma ação que ele levaria recusa ao tentar.
        """
        status = SaleStatus.from_value(venda.get("status", "CONCLUIDA"))
        permitido = can_reverse_sales(session) and status.reversivel
        for botao in (self.cancel_button, self.return_button):
            botao.setEnabled(permitido)
            botao.setVisible(can_reverse_sales(session))
```

Cada ação abre um diálogo que **exige** o motivo antes de emitir o sinal:

```python
    def _pedir_motivo(self, titulo, rotulo):
        texto, confirmou = QInputDialog.getText(self, titulo, rotulo)
        if not confirmou:
            return None
        if not texto.strip():
            QMessageBox.warning(self, titulo, "Informe o motivo da operação.")
            return None
        return texto.strip()
```

- [ ] **Step 4: Ligar o botão de detalhe na listagem**

Em `vendas.py`, acrescentar `detalhes_requested = Signal(str)` e, em `atualizar_tabela_historico`, uma coluna de ação com o botão de olho, no molde de `movimentacoes.py:970-991`:

```python
            detalhes = QPushButton()
            detalhes.setIcon(qta.icon("fa5s.eye", color="#1D4ED8"))
            detalhes.setToolTip("Ver detalhes da venda")
            detalhes.setAccessibleName(f"Ver detalhes da venda {venda['id']}")
            detalhes.clicked.connect(
                lambda _=False, i=venda["id"]: self.detalhes_requested.emit(i)
            )
```

- [ ] **Step 5: Ligar na janela**

Em `main_window.py`:

```python
        self.sale_details_page = SaleDetailsPage()                    # junto da linha 179
        pages.addWidget(self.sale_details_page)                       # junto da linha 267
        self.vendas_page.detalhes_requested.connect(self._show_sale_details)
        self.sale_details_page.back_button.clicked.connect(
            lambda: self.show_page("vendas")
        )

    def _show_sale_details(self, sale_id):
        """Carrega do SERVIÇO, não da linha da tabela.

        A linha é uma foto do momento da consulta; o detalhe precisa do que
        está gravado agora, senão uma reversão feita noutra máquina some.
        """
        try:
            venda = self.sale_service.get_sale(self.session, sale_id)
        except Exception as erro:
            QMessageBox.warning(self, "Não foi possível abrir a venda", str(erro))
            return
        if venda is None:
            QMessageBox.information(
                self, "Venda não encontrada",
                "Esta venda não está mais disponível para esta empresa.",
            )
            return
        self.sale_details_page.load_sale(venda, self.session)
        self.pages.setCurrentWidget(self.sale_details_page)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_us17_detalhe_da_venda.py tests/test_page_loading.py -q`
Expected: PASS

- [ ] **Step 7: Commit (preparar e confirmar)**

Mensagem proposta: `feat(ui): add sale details page with items, payment and reversal link`
**Parar e pedir confirmação.**

---

### Task 9: Ações de cancelamento e devolução ligadas ao estoque

**Files:**
- Modify: `src/stockflow/presentation/windows/main_window.py` (handlers de reversão)
- Test: `tests/test_us17_reversao_de_venda.py`

**Interfaces:**
- Consumes: `SaleDetailsPage.cancel_requested`, `.return_requested`, `SaleService.cancel_sale`, `.return_sale`.
- Produces: `MainWindow._cancelar_venda(sale_id, reason)` e `._devolver_venda(sale_id, reason)`.

- [ ] **Step 1: Write the failing test**

Criar `tests/test_us17_reversao_de_venda.py`:

```python
"""Cancelar e devolver venda pela janela, com efeito no estoque (US17)."""

import pytest
from PySide6.QtWidgets import QMessageBox

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.windows.main_window import MainWindow


@pytest.fixture
def janela(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: QMessageBox.Ok)
    window = MainWindow(conta_por_papel(UserRole.ADMIN).session())
    yield window
    window.close()


def _vender(janela, codigo="PRD-009", quantidade=2):
    page = janela.vendas_page
    page._apontar_cliente(page.clientes[0]["id"])
    page.selecionar_produto(codigo)
    page.qtd_input.setText(str(quantidade))
    page.save_button.click()
    return page.historico_vendas[0]["id"]


def test_cancelar_devolve_o_saldo_ao_estoque(janela):
    antes = int(janela.products["PRD-009"].stock)
    venda = _vender(janela)
    assert int(janela.products["PRD-009"].stock) == antes - 2
    janela._cancelar_venda(venda, "registro em duplicidade")
    assert int(janela.products["PRD-009"].stock) == antes


def test_devolver_devolve_o_saldo_ao_estoque(janela):
    antes = int(janela.products["PRD-009"].stock)
    venda = _vender(janela)
    janela._devolver_venda(venda, "cliente desistiu")
    assert int(janela.products["PRD-009"].stock) == antes


def test_venda_cancelada_aparece_com_o_status_no_historico(janela):
    venda = _vender(janela)
    janela._cancelar_venda(venda, "engano")
    janela.vendas_page.reload_sales()
    linha = next(v for v in janela.vendas_page.historico_vendas if v["id"] == venda)
    assert linha["status"] == "CANCELADA"


def test_vinculo_guarda_motivo_e_especie(janela):
    venda = _vender(janela)
    janela._devolver_venda(venda, "produto com defeito")
    gravado = janela.sale_service.get_sale(janela.session, venda)
    assert gravado["reversal_kind"] == "DEVOLUCAO"
    assert gravado["reversal_reason"] == "produto com defeito"


def test_reverter_duas_vezes_e_recusado(janela):
    venda = _vender(janela)
    janela._cancelar_venda(venda, "engano")
    antes = int(janela.products["PRD-009"].stock)
    janela._devolver_venda(venda, "segunda tentativa")
    assert int(janela.products["PRD-009"].stock) == antes


def test_vendedor_nao_reverte(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    window = MainWindow(conta_por_papel(UserRole.SELLER).session())
    try:
        venda = _vender(window)
        with pytest.raises(PermissionDeniedError):
            window.sale_service.cancel_sale(window.session, venda, "tentativa")
    finally:
        window.close()


def test_reversao_atualiza_a_tela_de_estoque(janela):
    venda = _vender(janela)
    antes = janela.estoque_page.table.rowCount()
    janela._cancelar_venda(venda, "engano")
    assert janela.estoque_page.table.rowCount() == antes
    assert int(janela.products["PRD-009"].stock) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_us17_reversao_de_venda.py -q`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_cancelar_venda'`

- [ ] **Step 3: Implementar os handlers**

Em `main_window.py`, junto dos demais handlers de operação:

```python
        self.sale_details_page.cancel_requested.connect(self._cancelar_venda)
        self.sale_details_page.return_requested.connect(self._devolver_venda)

    def _cancelar_venda(self, sale_id, reason):
        self._reverter_venda(self.sale_service.cancel_sale, sale_id, reason,
                             "cancelar")

    def _devolver_venda(self, sale_id, reason):
        self._reverter_venda(self.sale_service.return_sale, sale_id, reason,
                             "devolver")

    def _reverter_venda(self, operacao, sale_id, reason, acao):
        """Reverter mexe no SALDO, então reconsulta o catálogo junto.

        Mesma razão de `_venda_registrada`: deixar o estoque desatualizado
        depois de uma reversão faz a próxima venda ser recusada por um saldo
        que a tela diz existir.
        """
        try:
            operacao(self.session, sale_id, reason)
        except PermissionDeniedError as erro:
            QMessageBox.critical(self, "Acesso restrito", str(erro))
            return
        except Exception as erro:
            QMessageBox.warning(self, f"Não foi possível {acao} a venda", str(erro))
            return

        self.vendas_page.reload_sales()
        self._recarregar_catalogo()
        self.movimentacoes_page.reload_products()
        venda = self.sale_service.get_sale(self.session, sale_id)
        if venda is not None:
            self.sale_details_page.load_sale(venda, self.session)
```

Reaproveitar o método de recarga de catálogo que `_venda_registrada` já usa; não criar um segundo caminho.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_us17_reversao_de_venda.py -q`
Expected: PASS

- [ ] **Step 5: Commit (preparar e confirmar)**

Mensagem proposta: `feat(ui): wire sale cancellation and return to stock refresh`
**Parar e pedir confirmação.**

---

### Task 10: Totais de Dashboard e Relatórios sem vendas revertidas

**Files:**
- Modify: `src/stockflow/presentation/pages/dashboard.py:157-164`
- Modify: `src/stockflow/presentation/pages/reports.py:184-186, 218-222`
- Test: `tests/test_us17_totais_ignoram_revertidas.py`

**Interfaces:**
- Consumes: `SaleStatus.revertida` (Task 4); a chave `status` da linha de venda (Task 6).

- [ ] **Step 1: Write the failing test**

```python
"""Venda desfeita não é dinheiro vendido (US17).

A US17 não pediu isto, mas é ela que cria os estados CANCELADA e DEVOLVIDA:
sem esta exclusão, a própria história introduziria um número errado.
"""

import pytest

from stockflow.presentation.pages.dashboard import DashboardPage
from stockflow.presentation.pages.reports import ReportsPage


class VendasFalsas:
    def list_all(self):
        return [
            {"id": "1", "cliente": "Ana", "produto": "X", "valor": "R$ 100,00",
             "data": "01/10/2026", "total": "100.00", "status": "CONCLUIDA"},
            {"id": "2", "cliente": "Bia", "produto": "Y", "valor": "R$ 50,00",
             "data": "02/10/2026", "total": "50.00", "status": "CANCELADA"},
            {"id": "3", "cliente": "Cid", "produto": "Z", "valor": "R$ 30,00",
             "data": "03/10/2026", "total": "30.00", "status": "DEVOLVIDA"},
        ]


class ProdutosFalsos:
    def list_all(self):
        return []

    def load_catalog(self):
        return {}


def test_dashboard_soma_so_o_que_continua_vendido(qapp):
    page = DashboardPage(ProdutosFalsos(), VendasFalsas(), ProdutosFalsos())
    page.refresh()
    qapp.processEvents()
    try:
        assert "100,00" in page.total_vendido_label.text()
        assert "180,00" not in page.total_vendido_label.text()
    finally:
        page.close()


def test_relatorio_de_vendas_marca_as_revertidas(qapp):
    page = ReportsPage(ProdutosFalsos(), VendasFalsas())
    page.kind.setCurrentIndex(1)
    page.refresh()
    qapp.processEvents()
    try:
        assert "Status" in page.headers
        assert "100,00" in page.metrics[1][1].text()
    finally:
        page.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_us17_totais_ignoram_revertidas.py -q`
Expected: FAIL — o total soma 180,00

- [ ] **Step 3: Excluir revertidas dos totais**

Em `dashboard.py`, onde hoje está `total = sum((Decimal(str(sale['total'])) for sale in sales), Decimal(0))`:

```python
        # Venda cancelada ou devolvida não é receita. A contagem de operações
        # continua incluindo todas — o histórico aconteceu — mas o dinheiro,
        # não: somá-lo reportaria faturamento que foi desfeito.
        vendidas = [s for s in sales
                    if not SaleStatus.from_value(s.get("status", "CONCLUIDA")).revertida]
        total = sum((Decimal(str(s["total"])) for s in vendidas), Decimal(0))
```

Em `reports.py`, acrescentar `Status` aos cabeçalhos de venda e à tupla de linha, e aplicar o mesmo recorte no cálculo de `total` e `valor médio` dentro de `_apply_filters`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_us17_totais_ignoram_revertidas.py tests/test_dashboard_replenishment.py tests/test_reports_ui.py -q`
Expected: PASS

- [ ] **Step 5: Commit (preparar e confirmar)**

Mensagem proposta: `fix(ui): exclude reversed sales from revenue totals`
**Parar e pedir confirmação.**

---

### Task 11: Verificação contra PostgreSQL real e fechamento

**Files:**
- Modify: `scripts/verify_sales.py` (nova função `exercise_us17`, registrada em `run`)

**Interfaces:**
- Consumes: todas as anteriores.

- [ ] **Step 1: Escrever as checagens no ensaio real**

Acrescentar `exercise_us17(dsn)` a `scripts/verify_sales.py`, no molde de `exercise`, usando `check` e `rejects`. Cobrir, com conexões separadas por papel:

```python
    # Paginação: 120 vendas, páginas de 50, sem buraco nem repetição.
    vistos = []
    for offset in (0, 50, 100):
        pagina = seller.execute(
            "SELECT id, total_count FROM public.fn_list_sales(%s, p_limit=>50, p_offset=>%s)",
            (company, offset)).fetchall()
        check(pagina[0][1] == 120, 'The page total matches the filtered set')
        vistos += [linha[0] for linha in pagina]
    check(len(vistos) == len(set(vistos)) == 120,
          'Paging the real history neither repeats nor skips a sale')

    # Filtros combinados chegam ao WHERE.
    # Ordenação só aceita a lista fechada.
    rejects(lambda: seller.execute(
        "SELECT * FROM public.fn_list_sales(%s, p_sort=>%s)", (company, 'id; DROP')),
        '23514', 'An unknown sort order is refused instead of interpolated')

    # Alçada: só ADMIN reverte.
    rejects(lambda: seller_conn.execute(
        "SELECT public.fn_cancel_sale(%s, %s)", (sale, 'tentativa')),
        '42501', 'SELLER cannot cancel a sale')
    rejects(lambda: stock_conn.execute(
        "SELECT public.fn_return_sale(%s, %s)", (sale, 'tentativa')),
        '42501', 'STOCK cannot return a sale')

    # Motivo é obrigatório no banco também.
    rejects(lambda: admin_conn.execute(
        "SELECT public.fn_cancel_sale(%s, %s)", (sale, '   ')),
        '23514', 'A reversal without a reason is refused by the database')

    # Cancelar devolve o saldo; devolver também, por caminho diferente.
    # Reversão é terminal.
    rejects(lambda: admin_conn.execute(
        "SELECT public.fn_return_sale(%s, %s)", (sale, 'segunda')),
        '23514', 'A reversed sale cannot be reversed again')

    # Empresa alheia não enxerga nem reverte.
    rejects(lambda: outra_empresa.execute(
        "SELECT public.fn_cancel_sale(%s, %s)", (sale, 'invasão')),
        '42501', 'A sale from another company cannot be reversed')
    check(outra_empresa.execute(
        "SELECT count(*) FROM public.sale_reversals").fetchone()[0] == 0,
        'RLS hides sale reversals from an unaffiliated account')

    # O bloqueio da US12/SCRUM-223 continua de pé na tabela nova.
    rejects(lambda: admin_conn.execute(
        "INSERT INTO public.sale_reversals(company_id, sale_id, kind, reason) "
        "VALUES (%s,%s,'CANCELAMENTO','a mão')", (company, sale)),
        '42501', 'Not even an ADMIN writes a reversal by hand')
```

Registrar `exercise_us17` na tupla de cenários de `run()`.

- [ ] **Step 2: Rodar contra PostgreSQL local**

```bash
STOCKFLOW_TEST_DSN='host=127.0.0.1 port=55439 dbname=postgres user=postgres' \
  QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/verify_sales.py
```
Expected: todas as linhas `PASS`. Rodar também `scripts/verify_postgres.py` e `scripts/verify_postgres.py --schema` — os dois caminhos precisam passar, porque há defeitos que só quebram o declarativo.

- [ ] **Step 3: Suíte completa confrontada com o baseline**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: `1074 passed` mais os testes novos, `27 skipped`, **zero falhas**. Qualquer falha é nova e precisa ser explicada antes de seguir — não há falha herdada em `tests/`.

- [ ] **Step 4: Entregar a migration ao usuário**

Não aplicar. Reportar:

```
Migration pronta: database/supabase/migrations/20261024120000_us17_sales_history.sql
Para aplicar:  supabase db push
```

- [ ] **Step 5: Atualizar a memória do projeto**

Registrar no cérebro `StockFlow`, em `Memoria/Contexto persistente.md`, o padrão aprovado desta rodada: reversão como relação com índice único, cancelamento e devolução movendo estoque por mecanismos diferentes, e o novo baseline da suíte.

- [ ] **Step 6: Commit (preparar e confirmar)**

Mensagem proposta: `test: verify US17 sales history and reversal against real PostgreSQL`
**Parar e pedir confirmação.**

---

## Self-Review

**Cobertura da spec:**

| Requisito da spec | Task |
|---|---|
| Paginação real com total | 2, 6, 7 |
| Ordem cronológica com desempate | 2 |
| Filtros combináveis, preservados ao paginar | 2, 6, 7 |
| Ordenação por lista fechada | 2, 5, 7 |
| Tela de detalhes completa | 8 |
| Cancelamento e devolução com motivo | 3, 5, 8, 9 |
| Vínculo visível e persistido | 1, 2, 6, 8 |
| Edição continua bloqueada | 1 (grant), 7 e 8 (NoEditTriggers), 11 (prova real) |
| Permissões nas duas camadas | 3, 4, 5, 11 |
| Totais sem vendas revertidas | 10 |

**Consistência de tipos:** `SaleFilter`/`SalePage` definidos na Task 5 e usados com os mesmos nomes de campo nas Tasks 6 e 7. `list_page(filtro, page, size)` idêntico na porta, nos dois adaptadores e no serviço. `cancel`/`revert` nos repositórios correspondem a `cancel_sale`/`return_sale` no serviço — nomes diferentes de propósito: o repositório persiste, o serviço autoriza.

**Riscos conhecidos:**

1. `#variable_conflict use_column` só falha na criação da função. A Task 2 verifica contra PostgreSQL real antes de seguir.
2. A Task 5 quebra os chamadores de `list_sales()` de propósito; as Tasks 6 e 7 consertam. Não fechar a Task 5 declarando a suíte verde.
3. `trg_max_value_verify` pode recusar a entrada compensatória da devolução quando o estoque máximo estiver no limite. A mensagem do banco é propagada; é comportamento correto, não defeito.
