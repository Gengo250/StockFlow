-- US23: manter exigência de caixa aberto em INSERT e em qualquer UPDATE.
-- DEFINER permite consultar o status sem conceder acesso direto ao log.
CREATE OR REPLACE FUNCTION public.trg_guard_sale_open_register()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_register_status text;
    v_company_id uuid;
    v_candidates uuid[];
    v_open_count integer;
BEGIN
    IF NEW.register_log_id IS NULL THEN
        -- Resolver candidatos em um snapshot: não escolher arbitrariamente
        -- o primeiro caso uma segunda sessão apareça entre count e SELECT.
        SELECT array_agg(id ORDER BY id) INTO v_candidates FROM public.register_log
         WHERE company_id = NEW.company_id AND status = 'OPEN';
        v_open_count := COALESCE(cardinality(v_candidates), 0);
        IF v_open_count = 0 THEN
            RAISE EXCEPTION 'A empresa precisa ter um caixa aberto para registrar vendas.';
        ELSIF v_open_count > 1 THEN
            RAISE EXCEPTION 'Há mais de um caixa aberto. Informe o caixa da venda.';
        END IF;
        NEW.register_log_id := v_candidates[1];
    END IF;
    -- Serializa com o fechamento e revalida o status após eventual espera.
    SELECT status, company_id INTO v_register_status, v_company_id
      FROM public.register_log WHERE id = NEW.register_log_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Sessão de caixa informada não existe.';
    END IF;
    IF v_company_id IS DISTINCT FROM NEW.company_id THEN
        RAISE EXCEPTION 'A sessão de caixa pertence a outra empresa.' USING ERRCODE = '42501';
    END IF;
    IF v_register_status <> 'OPEN' THEN
        RAISE EXCEPTION 'Não é permitido registrar ou alterar vendas em um caixa fechado.';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_validate_sale_open_register ON public.sales;
CREATE TRIGGER trg_validate_sale_open_register
    BEFORE INSERT OR UPDATE ON public.sales
    FOR EACH ROW EXECUTE FUNCTION public.trg_guard_sale_open_register();
