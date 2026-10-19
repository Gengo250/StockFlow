CREATE OR REPLACE VIEW public.vw_stock_situation
WITH (security_invoker = true) AS
SELECT
    p.company_id,
    p.id                                            AS product_id,
    p.name                                          AS product_name,
    p.stock                                         AS current_balance,
    ps.min_quantity                                 AS min_quantity,
    public.fn_stock_state(p.stock, ps.min_quantity) AS state,
    p.barcode AS product_code,
    ps.max_quantity                                 AS max_quantity,
    CASE
        WHEN ps.max_quantity IS NOT NULL AND p.stock <= COALESCE(ps.min_quantity, p.stock)
        THEN GREATEST(0, ps.max_quantity - p.stock)
        ELSE NULL
    END                                             AS suggested_replenishment_quantity
FROM public.products p
LEFT JOIN public.product_stock ps ON ps.product_id = p.id
WHERE p.active;
