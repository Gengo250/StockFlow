
CREATE OR REPLACE VIEW public.vw_stock_situation AS
SELECT
    p.id                              AS product_id,
    p.name,                           AS product_name
    p.stock,                          As current_balance
    COALESCE(ps.min_quantity, 0)      AS min_quantity,
    public.fn_stock_state(p.stock,ps.min_quantity) AS state,
FROM public.products p
LEFT JOIN public.product_stock ps ON ps.product_id = p.id;

