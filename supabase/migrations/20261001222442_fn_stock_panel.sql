
CREATE OR REPLACE FUNCTION public.fn_stock_panel()
RETURNS TABLE (
    company_state public.company_stock_state,
    total         int,
    criticos      int,
    baixos        int,
    atencao       int,
    normais       int
)
LANGUAGE sql STABLE AS $$
    WITH base AS (SELECT state FROM public.vw_stock_situation)
    SELECT
        public.fn_company_stock_state(),
        COUNT(*)::int,
        COUNT(*) FILTER (WHERE state = 'CRITICO')::int,
        COUNT(*) FILTER (WHERE state = 'BAIXO')::int,
        COUNT(*) FILTER (WHERE state = 'ATENCAO')::int,
        COUNT(*) FILTER (WHERE state = 'NORMAL')::int
    FROM base;
$$;