CREATE OR REPLACE FUNCTION public.fn_adjust_product_stock(
    p_product_id    uuid,
    p_company_id    uuid,
    p_quantity      integer, -- Sempre positivo (Ex: 10)
    p_movement_kind public.movement_kind, -- 'ENTRADA' ou 'SAIDA'
    p_justification  text
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_current_stock integer;
BEGIN
    -- 1. VALIDAÇÃO DE JUSTIFICATIVA 
    IF p_justification IS NULL OR btrim(p_justification) = '' THEN
        RAISE EXCEPTION 'Justificativa é obrigatória para ajustes manuais de estoque'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 2. VALIDAÇÃO DE PERMISSÃO (Apenas ADMIN ou STOCK)
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para realizar ajustes de estoque'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 3. VALIDAÇÃO DE SALDO ATUAL
    -- Buscamos o saldo para evitar que uma saída deixe o estoque negativo
    SELECT stock INTO v_current_stock FROM public.products WHERE id = p_product_id;

    IF v_current_stock IS NULL THEN
        RAISE EXCEPTION 'Produto não encontrado' USING ERRCODE = 'not_null_violation';
    END IF;

    -- 4. BLOQUEIO DE SALDO NEGATIVO (Se for Saída)
    IF p_movement_kind = 'SAIDA' AND (v_current_stock - p_quantity) < 0 THEN
        RAISE EXCEPTION 'Operação recusada: Saldo insuficiente. Saldo atual: %', v_current_stock
            USING ERRCODE = 'check_violation';
    END IF;

    -- 5. EXECUÇÃO DA MOVIMENTAÇÃO (A única escrita necessária)
    -- IMPORTANTE: Não fazemos UPDATE em public.products.
    -- O trigger 'trg_stock_movements_apply' cuidará de atualizar o saldo automaticamente.
    INSERT INTO public.stock_movements (
        product_id,
        company_id,
        quantity,
        kind,
        note,
        created_by,
        created_on,
        status
    ) VALUES (
        p_product_id,
        p_company_id,
        p_quantity,
        p_movement_kind,
        p_justification,
        public.fn_current_user_id(),
        now(),
        'CONFIRMADA'
    );

END;
$$;