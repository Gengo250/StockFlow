-- Corrige a função publicada sem RETURN na 20261018005557.
-- SECURITY INVOKER mantém o isolamento por empresa das políticas de leitura.
CREATE OR REPLACE FUNCTION public.fn_get_effective_max_stock(p_product_id uuid)
RETURNS integer
LANGUAGE sql STABLE SECURITY INVOKER
SET search_path = public AS $$
    SELECT COALESCE(ps.max_quantity, c.max_stock_limit)
      FROM public.products p
      JOIN public.company c ON c.id = p.company_id
      LEFT JOIN public.product_stock ps ON ps.product_id = p.id
     WHERE p.id = p_product_id;
$$;

-- Mesmo contrato de execução do schema declarativo.
REVOKE ALL ON FUNCTION public.fn_get_effective_max_stock(uuid),
    public.fn_set_max_stock(uuid, integer),
    public.fn_set_company_max_stock_limit(uuid, integer) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.fn_get_effective_max_stock(uuid),
    public.fn_set_max_stock(uuid, integer),
    public.fn_set_company_max_stock_limit(uuid, integer) TO authenticated, app_backend;
