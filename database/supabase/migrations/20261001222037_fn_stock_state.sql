CREATE OR REPLACE FUNCTION public.fn_stock_state(
    p_stock integer,
    p_min   integer
) RETURNS public.stock_state
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_min IS NULL OR p_min = 0 THEN 'NORMAL'::public.stock_state
        WHEN COALESCE(p_stock, 0) <= 0   THEN 'CRITICO'::public.stock_state
        WHEN p_stock <= p_min            THEN 'BAIXO'::public.stock_state
        WHEN p_stock <  p_min * 1.2      THEN 'ATENCAO'::public.stock_state
        ELSE                                  'NORMAL'::public.stock_state
    END;
$$;
