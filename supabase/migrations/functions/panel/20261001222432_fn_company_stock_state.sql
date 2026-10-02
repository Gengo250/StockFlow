CREATE OR REPLACE FUNCTION public.fn_company_stock_state()
RETURNS public.company_stock_state
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_total     int;
    v_critico   int;
    v_baixo     int;
    v_atencao   int;
    v_pct_baixo numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(*) FILTER (WHERE state = 'CRITICO'),
        COUNT(*) FILTER (WHERE state = 'BAIXO'),
        COUNT(*) FILTER (WHERE state = 'ATENCAO')
    INTO v_total, v_critico, v_baixo, v_atencao
    FROM public.vw_stock_situation;

    IF v_total = 0 THEN
        RETURN 'ATENCAO';
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