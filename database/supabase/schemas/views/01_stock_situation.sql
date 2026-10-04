-- Chama fn_stock_state (procedures/04_stock). O corpo de uma view é validado
-- na criação, por isso schema_paths lista procedures antes de views.
--
-- min_quantity sai da junção à esquerda SEM COALESCE: o NULL é informação,
-- não ausência a ser preenchida. Trocá-lo por zero aqui apagaria a diferença
-- entre "ninguém configurou" e "configurado como zero" antes mesmo de
-- fn_stock_state poder decidir, e todo produto sem configuração passaria a
-- alertar ao zerar o saldo.

CREATE OR REPLACE VIEW public.vw_stock_situation
WITH (security_invoker = true) AS
SELECT
    p.company_id,
    p.id                                            AS product_id,
    p.barcode                                       AS product_code,
    p.name                                          AS product_name,
    p.stock                                         AS current_balance,
    ps.min_quantity                                 AS min_quantity,
    public.fn_stock_state(p.stock, ps.min_quantity) AS state
FROM public.products p
LEFT JOIN public.product_stock ps ON ps.product_id = p.id
WHERE p.active;
