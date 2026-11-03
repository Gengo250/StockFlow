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
    v_dinheiro numeric(10,2) := 0.00;
    v_debito numeric(10,2) := 0.00;
    v_credito numeric(10,2) := 0.00;
    v_pix numeric(10,2) := 0.00;
    v_vale numeric(10,2) := 0.00;
    v_outro numeric(10,2) := 0.00;
    v_total_sales numeric(10,2) := 0.00;
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

    -- Agregação dos valores das vendas CONCLUIDAS no caixa
    SELECT 
        COALESCE(SUM(CASE WHEN payment_method = 'DINHEIRO' THEN total ELSE 0 END), 0.00),
        COALESCE(SUM(CASE WHEN payment_method = 'DEBITO' THEN total ELSE 0 END), 0.00),
        COALESCE(SUM(CASE WHEN payment_method = 'CREDITO' THEN total ELSE 0 END), 0.00),
        COALESCE(SUM(CASE WHEN payment_method = 'PIX' THEN total ELSE 0 END), 0.00),
        COALESCE(SUM(CASE WHEN payment_method = 'VALE' THEN total ELSE 0 END), 0.00),
        COALESCE(SUM(CASE WHEN payment_method = 'OUTRO' THEN total ELSE 0 END), 0.00)
    INTO v_dinheiro, v_debito, v_credito, v_pix, v_vale, v_outro
    FROM public.sales
    WHERE register_log_id = p_register_log_id 
      AND status = 'CONCLUIDA'::sale_status;

    v_total_sales := v_dinheiro + v_debito + v_credito + v_pix + v_vale + v_outro;
    v_total_expected := v_log.initial_balance + v_total_sales;
    v_total_declared := COALESCE(p_declared_dinheiro, 0) + 
                        COALESCE(p_declared_debito, 0) + 
                        COALESCE(p_declared_credito, 0) + 
                        COALESCE(p_declared_pix, 0) + 
                        COALESCE(p_declared_vale, 0) + 
                        COALESCE(p_declared_outro, 0);

    v_diff := v_total_declared - v_total_expected;

    IF v_diff <> 0.00 AND (p_justification IS NULL OR trim(p_justification) = '') THEN
        RAISE EXCEPTION 'Divergência de valores detectada (Diferença: %). É obrigatório informar uma justificativa.', v_diff;
    END IF;

    UPDATE public.register_log
    SET status = 'CLOSED',
        closed_at = now(),
        total_dinheiro = v_dinheiro,
        total_debito = v_debito,
        total_credito = v_credito,
        total_pix = v_pix,
        total_vale = v_vale,
        total_outro = v_outro,
        total_sales = v_total_sales,
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
        'total_sales', v_total_sales,
        'total_expected', v_total_expected,
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
GRANT EXECUTE ON FUNCTION public.fn_open_register_session(uuid,uuid,uuid,uuid,numeric) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fn_close_register_session(uuid,numeric,numeric,numeric,numeric,numeric,numeric,text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fn_current_register_session(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fn_start_my_register(uuid,numeric) TO authenticated;
