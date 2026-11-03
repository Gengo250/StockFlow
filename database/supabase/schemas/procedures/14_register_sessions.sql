-- US23: RPCs autorizadas de caixa. Objetos qualificados e search_path restrito.
CREATE OR REPLACE FUNCTION public.fn_open_register_session(
    p_company_id uuid,
    p_register_id uuid,
    p_operator_id uuid,
    p_session_id uuid,
    p_initial_balance numeric
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
    v_new_log_id uuid;
    v_constraint text;
BEGIN
    IF v_actor IS NULL
       OR p_operator_id IS DISTINCT FROM v_actor
       OR NOT public.fn_has_role(
            p_company_id, ARRAY['ADMIN', 'SELLER']::public.user_role[]
       ) THEN
        RAISE EXCEPTION 'Apenas um administrador ou vendedor ativo da empresa pode abrir o caixa.'
            USING ERRCODE = '42501';
    END IF;
    IF p_initial_balance IS NULL OR p_initial_balance < 0
       OR p_initial_balance::text IN ('NaN', 'Infinity', '-Infinity')
       OR p_initial_balance >= 100000000
       OR p_initial_balance <> round(p_initial_balance, 2) THEN
        RAISE EXCEPTION 'Saldo inicial deve ser finito, não negativo e ter até duas casas decimais.';
    END IF;
    PERFORM r.id FROM public.register r WHERE r.id = p_register_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Caixa não encontrado.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.register_log
         WHERE operator_id = p_operator_id AND status = 'OPEN'
    ) THEN
        RAISE EXCEPTION 'Operador já possui uma sessão de caixa aberta simultaneamente.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.register_log
         WHERE register_id = p_register_id AND status = 'OPEN'
    ) THEN
        RAISE EXCEPTION 'Este caixa físico já se encontra com uma sessão aberta.';
    END IF;
    BEGIN
        INSERT INTO public.register_log (
            company_id, register_id, operator_id, session_id, initial_balance, status, opened_at
        ) VALUES (
            p_company_id, p_register_id, p_operator_id, p_session_id, p_initial_balance, 'OPEN', now()
        ) RETURNING id INTO v_new_log_id;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint = 'idx_register_log_operator_open' THEN
            RAISE EXCEPTION 'Operador já possui uma sessão de caixa aberta simultaneamente.';
        ELSIF v_constraint = 'idx_register_log_register_open' THEN
            RAISE EXCEPTION 'Este caixa físico já se encontra com uma sessão aberta.';
        ELSE
            RAISE;
        END IF;
    END;
    UPDATE public.register SET change = p_initial_balance, logged_on = now(), session_id = p_session_id
     WHERE id = p_register_id;
    RETURN v_new_log_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_close_register_session(
    p_register_log_id uuid,
    p_declared_dinheiro numeric DEFAULT 0.00,
    p_declared_debito numeric DEFAULT 0.00,
    p_declared_credito numeric DEFAULT 0.00,
    p_declared_pix numeric DEFAULT 0.00,
    p_declared_vale numeric DEFAULT 0.00,
    p_declared_outro numeric DEFAULT 0.00,
    p_justification text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_log public.register_log%ROWTYPE;
    v_actor uuid := public.fn_current_user_id();
    v_dinheiro numeric;
    v_debito numeric;
    v_credito numeric;
    v_pix numeric;
    v_vale numeric;
    v_outro numeric;
    v_total_sales numeric;
    v_total_declared numeric;
    v_total_expected numeric;
    v_diff numeric;
BEGIN
    SELECT * INTO v_log FROM public.register_log WHERE id = p_register_log_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Sessão de caixa não encontrada.';
    END IF;
    IF v_actor IS NULL
       OR NOT public.fn_has_role(
            v_log.company_id, ARRAY['ADMIN', 'SELLER']::public.user_role[]
       )
       OR (
            v_log.operator_id IS DISTINCT FROM v_actor
            AND NOT public.fn_is_admin(v_actor, v_log.company_id)
       ) THEN
        RAISE EXCEPTION 'Sem permissão para fechar esta sessão de caixa.'
            USING ERRCODE = '42501';
    END IF;
    IF v_log.status = 'CLOSED' THEN
        RAISE EXCEPTION 'Esta sessão de caixa já se encontra fechada.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM (VALUES
            (COALESCE(p_declared_dinheiro, 0)), (COALESCE(p_declared_debito, 0)),
            (COALESCE(p_declared_credito, 0)), (COALESCE(p_declared_pix, 0)),
            (COALESCE(p_declared_vale, 0)), (COALESCE(p_declared_outro, 0))
        ) AS declared(amount)
        WHERE amount < 0 OR amount::text IN ('NaN', 'Infinity', '-Infinity')
           OR amount >= 100000000 OR amount <> round(amount, 2)
    ) THEN
        RAISE EXCEPTION 'Valores declarados devem ser finitos, não negativos e ter até duas casas decimais.';
    END IF;
    SELECT
        COALESCE(SUM(CASE WHEN s.payment_method = 'DINHEIRO' THEN s.total ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN s.payment_method = 'DEBITO' THEN s.total ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN s.payment_method = 'CREDITO' THEN s.total ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN s.payment_method = 'PIX' THEN s.total ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN s.payment_method = 'VALE' THEN s.total ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN s.payment_method = 'OUTRO' THEN s.total ELSE 0 END), 0)
      INTO v_dinheiro, v_debito, v_credito, v_pix, v_vale, v_outro
      FROM public.sales s
     WHERE s.register_log_id = p_register_log_id AND s.status = 'CONCLUIDA'::public.sale_status;
    v_total_sales := v_dinheiro + v_debito + v_credito + v_pix + v_vale + v_outro;
    v_total_expected := v_log.initial_balance + v_total_sales;
    v_total_declared := COALESCE(p_declared_dinheiro, 0) + COALESCE(p_declared_debito, 0)
        + COALESCE(p_declared_credito, 0) + COALESCE(p_declared_pix, 0)
        + COALESCE(p_declared_vale, 0) + COALESCE(p_declared_outro, 0);
    IF v_total_expected::text IN ('NaN', 'Infinity', '-Infinity')
       OR v_total_expected < 0 OR v_total_expected >= 100000000
       OR v_total_declared >= 100000000 THEN
        RAISE EXCEPTION 'Totais do caixa não conciliam ou excedem o limite monetário permitido.';
    END IF;
    v_diff := v_total_declared - v_total_expected;
    IF (
        COALESCE(p_declared_dinheiro, 0) <> v_log.initial_balance + v_dinheiro
        OR COALESCE(p_declared_debito, 0) <> v_debito
        OR COALESCE(p_declared_credito, 0) <> v_credito
        OR COALESCE(p_declared_pix, 0) <> v_pix
        OR COALESCE(p_declared_vale, 0) <> v_vale
        OR COALESCE(p_declared_outro, 0) <> v_outro
    ) AND (p_justification IS NULL OR btrim(p_justification) !~ '[^[:space:]]') THEN
        RAISE EXCEPTION 'Divergência por forma de pagamento detectada (Diferença total: %). É obrigatório informar uma justificativa.', v_diff;
    END IF;
    UPDATE public.register_log SET
        status = 'CLOSED', closed_at = now(),
        total_dinheiro = v_dinheiro, total_debito = v_debito, total_credito = v_credito,
        total_pix = v_pix, total_vale = v_vale, total_outro = v_outro, total_sales = v_total_sales,
        declared_dinheiro = COALESCE(p_declared_dinheiro, 0),
        declared_debito = COALESCE(p_declared_debito, 0),
        declared_credito = COALESCE(p_declared_credito, 0),
        declared_pix = COALESCE(p_declared_pix, 0),
        declared_vale = COALESCE(p_declared_vale, 0),
        declared_outro = COALESCE(p_declared_outro, 0),
        total_declared = v_total_declared, difference = v_diff, justification = p_justification
     WHERE id = p_register_log_id;
    UPDATE public.register SET session_id = NULL WHERE id = v_log.register_id;
    RETURN jsonb_build_object(
        'register_log_id', p_register_log_id, 'status', 'CLOSED',
        'initial_balance', v_log.initial_balance, 'total_sales', v_total_sales,
        'total_expected', v_total_expected, 'total_declared', v_total_declared, 'difference', v_diff
    );
END;
$$;
