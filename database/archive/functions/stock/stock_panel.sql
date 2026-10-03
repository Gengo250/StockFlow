CREATE OR REPLACE FUNCTION public.fn_stock_panel(p_company_id uuid)
RETURNS TABLE (
    company_state public.company_stock_state,
    total         int,
    criticos      int,
    baixos        int,
    atencao       int,
    normais       int
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Sem acesso a esta empresa' USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN QUERY
    SELECT public.fn_company_stock_state(p_company_id),
           COUNT(*)::int,
           COUNT(*) FILTER (WHERE v.state = 'CRITICO')::int,
           COUNT(*) FILTER (WHERE v.state = 'BAIXO')::int,
           COUNT(*) FILTER (WHERE v.state = 'ATENCAO')::int,
           COUNT(*) FILTER (WHERE v.state = 'NORMAL')::int
      FROM public.vw_stock_situation v
     WHERE v.company_id = p_company_id;
END;
$$;
