
CREATE OR REPLACE FUNCTION public.fn_company_stock_state(p_company_id uuid)
RETURNS public.company_stock_state
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_total     int;
    v_critico   int;
    v_baixo     int;
    v_atencao   int;
    v_pct_baixo numeric;
BEGIN
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Sem acesso a esta empresa' USING ERRCODE = 'insufficient_privilege';
    END IF;

    SELECT COUNT(*),
           COUNT(*) FILTER (WHERE state = 'CRITICO'),
           COUNT(*) FILTER (WHERE state = 'BAIXO'),
           COUNT(*) FILTER (WHERE state = 'ATENCAO')
      INTO v_total, v_critico, v_baixo, v_atencao
      FROM public.vw_stock_situation
     WHERE company_id = p_company_id;

    IF v_total = 0 THEN
        RETURN 'SEGURO';
    END IF;

    v_pct_baixo := (v_baixo::numeric / v_total) * 100;

    IF v_critico > 0 THEN
        RETURN 'CRITICO';
    ELSIF v_pct_baixo >= 20 THEN
        RETURN 'ALERTA';
    ELSIF v_baixo > 0 OR v_atencao > 0 THEN
        RETURN 'ATENCAO';
    ELSE
        RETURN 'SEGURO';
    END IF;
END;
$$;
