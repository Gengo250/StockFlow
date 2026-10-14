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
                    WHERE conrelid = 'public.stock_movements'::regclass
                      AND conname = 'ck_movements_counted_balance') THEN
        ALTER TABLE public.stock_movements
            ADD CONSTRAINT ck_movements_counted_balance
            CHECK (counted_balance IS NULL OR counted_balance >= 0);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.stock_movements'::regclass
                      AND conname = 'ck_movements_adjustment_pair') THEN
        ALTER TABLE public.stock_movements
            ADD CONSTRAINT ck_movements_adjustment_pair CHECK (
                (adjustment_reason IS NULL     AND counted_balance IS NULL)
             OR (adjustment_reason IS NOT NULL AND counted_balance IS NOT NULL));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.stock_movements'::regclass
                      AND conname = 'ck_movements_adjustment_detail') THEN
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
