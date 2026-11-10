CREATE OR REPLACE FUNCTION public.fn_open_register_session(
    p_company_id uuid,
    p_register_id uuid,
    p_operator_id uuid,
    p_session_id uuid,
    p_initial_balance numeric
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_new_log_id uuid;
BEGIN
    IF public.fn_current_user_id() IS NULL
       OR p_operator_id IS DISTINCT FROM public.fn_current_user_id()
       OR NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para abrir este caixa.' USING ERRCODE = '42501';
    END IF;
    IF EXISTS (SELECT 1 FROM public.register_log WHERE register_id=p_register_id AND company_id<>p_company_id) THEN
        RAISE EXCEPTION 'Caixa pertence a outra empresa.' USING ERRCODE = '42501';
    END IF;
    IF p_initial_balance IS NULL OR p_initial_balance::text IN ('NaN','Infinity','-Infinity')
       OR p_initial_balance <> round(p_initial_balance,2) THEN
        RAISE EXCEPTION 'Saldo inicial inválido.';
    END IF;
    IF p_initial_balance < 0 THEN
        RAISE EXCEPTION 'O saldo inicial não pode ser negativo.';
    END IF;

    -- Impede operador de ter mais de uma sessão aberta simultaneamente
    IF EXISTS (
        SELECT 1 FROM public.register_log 
        WHERE operator_id = p_operator_id AND status = 'OPEN'
    ) THEN
        RAISE EXCEPTION 'Operador já possui uma sessão de caixa aberta simultaneamente.';
    END IF;

    -- Impede o mesmo terminal de caixa de ser aberto mais de uma vez
    IF EXISTS (
        SELECT 1 FROM public.register_log 
        WHERE register_id = p_register_id AND status = 'OPEN'
    ) THEN
        RAISE EXCEPTION 'Este caixa físico já se encontra com uma sessão aberta.';
    END IF;

    INSERT INTO public.register_log (
        company_id,
        register_id,
        operator_id,
        session_id,
        initial_balance,
        status,
        opened_at
    ) VALUES (
        p_company_id,
        p_register_id,
        p_operator_id,
        p_session_id,
        p_initial_balance,
        'OPEN',
        now()
    ) RETURNING id INTO v_new_log_id;

    -- Atualiza o saldo (change) no registro do caixa
    UPDATE public.register
    SET change = p_initial_balance,
        logged_on = now(),
        session_id = p_session_id
    WHERE id = p_register_id;

    RETURN v_new_log_id;
END;
$$;

-- Fechamento automatizado: soma as vendas CONCLUIDAS da sessão por forma de
-- pagamento e, em seguida, soma esses subtotais (total geral das vendas).
-- Fonte única do cálculo, usada pela prévia e pelo fechamento.
CREATE OR REPLACE FUNCTION public.fn_register_payment_totals(p_register_log_id uuid)
RETURNS TABLE (
    total_dinheiro numeric(10,2),
    total_debito numeric(10,2),
    total_credito numeric(10,2),
    total_pix numeric(10,2),
    total_vale numeric(10,2),
    total_outro numeric(10,2),
    total_sales numeric(10,2)
)
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT dinheiro, debito, credito, pix, vale, outro,
           -- Total dos totais: soma dos subtotais de cada forma de pagamento.
           (dinheiro + debito + credito + pix + vale + outro)::numeric(10,2)
    FROM (
        SELECT
            COALESCE(SUM(s.total) FILTER (WHERE s.payment_method = 'DINHEIRO'), 0)::numeric(10,2) AS dinheiro,
            COALESCE(SUM(s.total) FILTER (WHERE s.payment_method = 'DEBITO'),   0)::numeric(10,2) AS debito,
            COALESCE(SUM(s.total) FILTER (WHERE s.payment_method = 'CREDITO'),  0)::numeric(10,2) AS credito,
            COALESCE(SUM(s.total) FILTER (WHERE s.payment_method = 'PIX'),      0)::numeric(10,2) AS pix,
            COALESCE(SUM(s.total) FILTER (WHERE s.payment_method = 'VALE'),     0)::numeric(10,2) AS vale,
            COALESCE(SUM(s.total) FILTER (WHERE s.payment_method = 'OUTRO'),    0)::numeric(10,2) AS outro
        FROM public.sales s
        WHERE s.register_log_id = p_register_log_id
          AND s.status = 'CONCLUIDA'::public.sale_status
    ) AS subtotais;
$$;

-- Prévia do fechamento: permite à aplicação exibir os totais calculados antes
-- da conferência. Sessão fechada devolve o retrato gravado no fechamento.
CREATE OR REPLACE FUNCTION public.fn_register_session_summary(p_register_log_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_log public.register_log%ROWTYPE;
    v_totals record;
    v_result jsonb;
BEGIN
    SELECT * INTO v_log FROM public.register_log WHERE id = p_register_log_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Sessão de caixa não encontrada.';
    END IF;

    -- O próprio operador consulta sua sessão; o ADMIN consulta qualquer sessão da empresa.
    IF public.fn_current_user_id() IS NULL
       OR NOT (
           (v_log.operator_id = public.fn_current_user_id()
            AND public.fn_has_role(v_log.company_id, ARRAY['ADMIN','SELLER']::public.user_role[]))
           OR public.fn_has_role(v_log.company_id, ARRAY['ADMIN']::public.user_role[])
       ) THEN
        RAISE EXCEPTION 'Sem permissão para consultar este caixa.' USING ERRCODE = '42501';
    END IF;

    IF v_log.status = 'CLOSED' THEN
        SELECT v_log.total_dinheiro AS total_dinheiro, v_log.total_debito AS total_debito,
               v_log.total_credito AS total_credito, v_log.total_pix AS total_pix,
               v_log.total_vale AS total_vale, v_log.total_outro AS total_outro,
               v_log.total_sales AS total_sales
        INTO v_totals;
    ELSE
        SELECT * INTO v_totals FROM public.fn_register_payment_totals(p_register_log_id);
    END IF;

    v_result := jsonb_build_object(
        'register_log_id', v_log.id,
        'status', v_log.status,
        'opened_at', v_log.opened_at,
        'closed_at', v_log.closed_at,
        'initial_balance', v_log.initial_balance,
        'totals', jsonb_build_object(
            'DINHEIRO', v_totals.total_dinheiro,
            'DEBITO', v_totals.total_debito,
            'CREDITO', v_totals.total_credito,
            'PIX', v_totals.total_pix,
            'VALE', v_totals.total_vale,
            'OUTRO', v_totals.total_outro
        ),
        'total_sales', v_totals.total_sales,
        -- O troco inicial fica na gaveta junto com o dinheiro das vendas.
        'expected_dinheiro', v_log.initial_balance + v_totals.total_dinheiro,
        'total_expected', v_log.initial_balance + v_totals.total_sales
    );

    IF v_log.status = 'CLOSED' THEN
        v_result := v_result || jsonb_build_object(
            'declared', jsonb_build_object(
                'DINHEIRO', v_log.declared_dinheiro,
                'DEBITO', v_log.declared_debito,
                'CREDITO', v_log.declared_credito,
                'PIX', v_log.declared_pix,
                'VALE', v_log.declared_vale,
                'OUTRO', v_log.declared_outro
            ),
            'total_declared', v_log.total_declared,
            'difference', v_log.difference,
            'justification', v_log.justification
        );
    END IF;

    RETURN v_result;
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
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_log public.register_log%ROWTYPE;
    v_totals record;
    v_total_declared numeric(10,2) := 0.00;
    v_total_expected numeric(10,2) := 0.00;
    v_diff numeric(10,2) := 0.00;
BEGIN
    SELECT * INTO v_log 
    FROM public.register_log 
    WHERE id = p_register_log_id 
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Sessão de caixa não encontrada.';
    END IF;

    IF public.fn_current_user_id() IS NULL
       OR v_log.operator_id IS DISTINCT FROM public.fn_current_user_id()
       OR NOT public.fn_has_role(v_log.company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para fechar este caixa.' USING ERRCODE = '42501';
    END IF;
    IF EXISTS (SELECT 1 FROM unnest(ARRAY[p_declared_dinheiro,p_declared_debito,p_declared_credito,
        p_declared_pix,p_declared_vale,p_declared_outro]) AS amount
        WHERE amount IS NULL OR amount < 0 OR amount::text IN ('NaN','Infinity','-Infinity')
           OR amount <> round(amount,2)) THEN
        RAISE EXCEPTION 'Valores declarados inválidos.';
    END IF;
    IF v_log.status = 'CLOSED' THEN
        RAISE EXCEPTION 'Esta sessão de caixa já se encontra fechada.';
    END IF;

    -- Totais automáticos por forma de pagamento e total dos totais.
    -- O FOR UPDATE acima serializa com o trigger de vendas: nenhuma venda
    -- entra na sessão entre este cálculo e o fechamento.
    SELECT * INTO v_totals FROM public.fn_register_payment_totals(p_register_log_id);

    v_total_expected := v_log.initial_balance + v_totals.total_sales;
    v_total_declared := p_declared_dinheiro + p_declared_debito + p_declared_credito
                      + p_declared_pix + p_declared_vale + p_declared_outro;
    v_diff := v_total_declared - v_total_expected;

    IF v_diff <> 0.00 AND (p_justification IS NULL OR trim(p_justification) = '') THEN
        RAISE EXCEPTION 'Divergência de valores detectada (Diferença: %). É obrigatório informar uma justificativa.', v_diff;
    END IF;

    UPDATE public.register_log
    SET status = 'CLOSED',
        closed_at = now(),
        total_dinheiro = v_totals.total_dinheiro,
        total_debito = v_totals.total_debito,
        total_credito = v_totals.total_credito,
        total_pix = v_totals.total_pix,
        total_vale = v_totals.total_vale,
        total_outro = v_totals.total_outro,
        total_sales = v_totals.total_sales,
        declared_dinheiro = p_declared_dinheiro,
        declared_debito = p_declared_debito,
        declared_credito = p_declared_credito,
        declared_pix = p_declared_pix,
        declared_vale = p_declared_vale,
        declared_outro = p_declared_outro,
        total_declared = v_total_declared,
        difference = v_diff,
        justification = p_justification
    WHERE id = p_register_log_id;

    -- Zera a sessão ativa do terminal
    UPDATE public.register
    SET session_id = NULL
    WHERE id = v_log.register_id;

    RETURN jsonb_build_object(
        'register_log_id', p_register_log_id,
        'status', 'CLOSED',
        'initial_balance', v_log.initial_balance,
        'totals', jsonb_build_object(
            'DINHEIRO', v_totals.total_dinheiro,
            'DEBITO', v_totals.total_debito,
            'CREDITO', v_totals.total_credito,
            'PIX', v_totals.total_pix,
            'VALE', v_totals.total_vale,
            'OUTRO', v_totals.total_outro
        ),
        'total_sales', v_totals.total_sales,
        'expected_dinheiro', v_log.initial_balance + v_totals.total_dinheiro,
        'total_expected', v_total_expected,
        'declared', jsonb_build_object(
            'DINHEIRO', p_declared_dinheiro,
            'DEBITO', p_declared_debito,
            'CREDITO', p_declared_credito,
            'PIX', p_declared_pix,
            'VALE', p_declared_vale,
            'OUTRO', p_declared_outro
        ),
        'total_declared', v_total_declared,
        'difference', v_diff
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_current_register_session(p_company_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE result jsonb;
BEGIN
    IF public.fn_current_user_id() IS NULL OR NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para consultar o caixa.' USING ERRCODE='42501';
    END IF;
    SELECT jsonb_build_object('id',id,'initial_balance',initial_balance,'status',status,'opened_at',opened_at)
    INTO result FROM public.register_log
    WHERE company_id=p_company_id AND operator_id=public.fn_current_user_id() AND status='OPEN';
    RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public.fn_start_my_register(p_company_id uuid,p_initial_balance numeric)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE terminal uuid;
BEGIN
    IF public.fn_current_user_id() IS NULL OR NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para iniciar caixa.' USING ERRCODE='42501';
    END IF;
    SELECT register_id INTO terminal FROM public.register_log
    WHERE company_id=p_company_id AND operator_id=public.fn_current_user_id()
    ORDER BY opened_at DESC LIMIT 1;
    IF terminal IS NULL THEN
        INSERT INTO public.register DEFAULT VALUES RETURNING id INTO terminal;
    END IF;
    PERFORM public.fn_open_register_session(p_company_id,terminal,public.fn_current_user_id(),NULL,p_initial_balance);
    RETURN public.fn_current_register_session(p_company_id);
END $$;

CREATE OR REPLACE FUNCTION public.trg_guard_sale_open_register()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE log public.register_log%ROWTYPE;
BEGIN
    IF TG_OP='UPDATE' AND NEW.register_log_id IS DISTINCT FROM OLD.register_log_id THEN
        RAISE EXCEPTION 'Não é permitido mudar o caixa de uma venda.';
    END IF;
    IF TG_OP='INSERT' AND NEW.register_log_id IS NULL THEN
        SELECT id INTO NEW.register_log_id FROM public.register_log
        WHERE company_id=NEW.company_id AND operator_id=NEW.created_by AND status='OPEN';
    END IF;
    IF NEW.register_log_id IS NULL THEN
        RAISE EXCEPTION 'Inicie o caixa antes de registrar a venda.';
    END IF;
    -- Mesmo bloqueio do fechamento: uma venda nunca entra após a conferência.
    SELECT * INTO log FROM public.register_log WHERE id=NEW.register_log_id FOR UPDATE;
    IF NOT FOUND OR log.company_id IS DISTINCT FROM NEW.company_id
       OR log.operator_id IS DISTINCT FROM NEW.created_by THEN
        RAISE EXCEPTION 'Sessão de caixa inválida para esta venda.';
    END IF;
    IF log.status <> 'OPEN' THEN
        RAISE EXCEPTION 'Não é permitido registrar ou alterar vendas em um caixa fechado.';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_validate_sale_open_register ON public.sales;
CREATE TRIGGER trg_validate_sale_open_register BEFORE INSERT OR UPDATE ON public.sales
FOR EACH ROW EXECUTE FUNCTION public.trg_guard_sale_open_register();

REVOKE ALL ON FUNCTION public.fn_open_register_session(uuid,uuid,uuid,uuid,numeric) FROM PUBLIC,anon;
REVOKE ALL ON FUNCTION public.fn_close_register_session(uuid,numeric,numeric,numeric,numeric,numeric,numeric,text) FROM PUBLIC,anon;
REVOKE ALL ON FUNCTION public.fn_current_register_session(uuid) FROM PUBLIC,anon;
REVOKE ALL ON FUNCTION public.fn_start_my_register(uuid,numeric) FROM PUBLIC,anon;
REVOKE ALL ON FUNCTION public.fn_register_payment_totals(uuid) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.fn_register_session_summary(uuid) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.fn_open_register_session(uuid,uuid,uuid,uuid,numeric) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fn_close_register_session(uuid,numeric,numeric,numeric,numeric,numeric,numeric,text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fn_current_register_session(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fn_start_my_register(uuid,numeric) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fn_register_session_summary(uuid) TO authenticated;
