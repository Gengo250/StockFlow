CREATE OR REPLACE VIEW public.vw_stock_situation
WITH (security_invoker = true) AS
SELECT
    p.company_id,
    p.id                                   AS product_id,
    p.name                                 AS product_name,
    p.stock                                AS current_balance,
    COALESCE(ps.min_quantity, 0)           AS min_quantity,
    public.fn_stock_state(p.stock, COALESCE(ps.min_quantity, 0)) AS state
FROM public.products p
LEFT JOIN public.product_stock ps ON ps.product_id = p.id
WHERE p.active;
