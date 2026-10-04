-- Chama vw_stock_situation (views/01), por isso o sufixo 02.
-- A US04 em uma consulta: produtos ATIVOS, com mínimo CONFIGURADO, cujo saldo
-- é menor ou igual a esse mínimo. O `<=` é o que inclui o saldo igual ao
-- mínimo; o `IS NOT NULL` no mínimo é o que exclui quem não tem configuração.
--
-- O filtro era `> 0` e passava por configurado. Com mínimo zero agora sendo
-- uma escolha explícita — alertar só quando acabar —, `> 0` silenciava
-- justamente quem pediu esse alerta. Quem não configurou nada tem NULL e
-- continua de fora.
CREATE OR REPLACE VIEW public.vw_stock_alerts
WITH (security_invoker = true) AS
SELECT
    s.company_id,
    s.product_id,
    s.product_code,
    s.product_name,
    s.current_balance,
    s.min_quantity,
    s.state
FROM public.vw_stock_situation s
WHERE s.min_quantity IS NOT NULL
  AND s.current_balance <= s.min_quantity;
