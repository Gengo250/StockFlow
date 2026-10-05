-- `vw_stock_alerts` passa a carregar o código do produto.
--
-- POR QUE
--
-- A tela de alerta exibe "identificação, saldo, mínimo e situação", e a
-- identificação que o usuário lê e procura é o código (`PRD-007`), não o uuid
-- interno. A view entregava `product_id` e `product_name`, e por isso a tela
-- não tinha como consumi-la sem perder a primeira coluna — foi o que manteve
-- a regra de alerta duplicada em Python por mais tempo do que devia.
--
-- Com o código aqui, a consulta passa a ser auto-suficiente: tudo que a tela
-- mostra vem dela, e a decisão de quais produtos alertam deixa de ter uma
-- segunda implementação do lado da aplicação.
--
-- `vw_stock_situation` também ganha a coluna, porque é dela que a de alerta
-- deriva. Acrescentar só na de baixo exigiria repetir a ligação com o
-- catálogo, que é justamente o que a derivação evita.

CREATE OR REPLACE VIEW public.vw_stock_situation
WITH (security_invoker = true) AS
SELECT
    p.company_id,
    p.id                                            AS product_id,
    p.name                                          AS product_name,
    p.stock                                         AS current_balance,
    ps.min_quantity                                 AS min_quantity,
    public.fn_stock_state(p.stock, ps.min_quantity) AS state,
    p.barcode AS product_code
FROM public.products p
LEFT JOIN public.product_stock ps ON ps.product_id = p.id
WHERE p.active;

-- Os critérios da US04, inalterados: mínimo CONFIGURADO (o `IS NOT NULL`
-- separa ausente de zero) e saldo menor ou igual a ele (o `<=` é o que faz o
-- saldo igual ao mínimo entrar no alerta).
CREATE OR REPLACE VIEW public.vw_stock_alerts
WITH (security_invoker = true) AS
SELECT
    s.company_id,
    s.product_id,
    s.product_name,
    s.current_balance,
    s.min_quantity,
    s.state,
    s.product_code
FROM public.vw_stock_situation s
WHERE s.min_quantity IS NOT NULL
  AND s.current_balance <= s.min_quantity;

-- `CREATE OR REPLACE VIEW` preserva privilégios, mas refazer custa nada e
-- protege o caso de a view ter sido recriada à mão entre as migrations.
-- Nunca para PUBLIC nem anon.
GRANT SELECT ON public.vw_stock_situation, public.vw_stock_alerts
  TO app_backend, authenticated;

-- ============================================================ conferência
DO $$
DECLARE v_faltando text;
BEGIN
  SELECT string_agg(esperado.coluna, ', ')
    INTO v_faltando
    FROM (VALUES ('product_code'), ('current_balance'), ('min_quantity'), ('state'))
         AS esperado(coluna)
   WHERE NOT EXISTS (
       SELECT 1 FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.table_name = 'vw_stock_alerts'
          AND c.column_name = esperado.coluna
   );

  IF v_faltando IS NOT NULL THEN
    RAISE EXCEPTION 'vw_stock_alerts sem as colunas que a tela consome: %', v_faltando;
  END IF;
END $$;
