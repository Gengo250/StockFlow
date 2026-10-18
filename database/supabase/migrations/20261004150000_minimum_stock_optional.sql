-- Estoque minimo passa a ser OPCIONAL: ausente e zero deixam de ser a mesma coisa.
--
-- POR QUE
--
-- `product_stock.min_quantity` era `NOT NULL DEFAULT 0`. Com isso o numero
-- zero carrega dois significados incompativeis: "ninguem configurou minimo"
-- e "o minimo deste produto é zero, avise quando acabar".
-- A US03 pede que os dois sejam distinguiveis, e eles nao sao dentro de um
-- inteiro nao nulo - falta um terceiro valor, e esse valor e NULL.
--
-- Depois desta migration:
--   minimo NULL -> nunca alerta, em nenhum saldo;
--   minimo 0    -> alerta quando o saldo chega a zero;
--   minimo N>0  -> alerta quando o saldo chega a N.
--
-- DROP DEFAULT e DROP NOT NULL sao obrigatorios.
--
-- O gatilho `trg_products_create_stock` grava a linha de estoque de todo
-- produto novo sem citar `min_quantity`. Enquanto houvesse `DEFAULT 0`, cada
-- produto cadastrado nasceria com minimo ZERO EXPLICITO - que agora alerta -
-- e a caixa de entrada de alertas encheria de produto que ninguem configurou.
-- Tirar so o NOT NULL resolveria o tipo e manteria o bug.
--
-- BACKFILL 0 -> NULL
--
-- Toda linha que hoje tem zero foi gravada quando zero significava
-- "nao configurado": ou veio do default do gatilho, ou de uma tela que nao
-- oferecia a opcao de deixar em branco. Preservar como zero explicito
-- transformaria a migration em uma enxurrada de alertas retroativos.

-- 1. a coluna

ALTER TABLE public.product_stock ALTER COLUMN min_quantity DROP NOT NULL;
ALTER TABLE public.product_stock ALTER COLUMN min_quantity DROP DEFAULT;

UPDATE public.product_stock SET min_quantity = NULL WHERE min_quantity = 0;

-- 2. a classificacao
-- A ORDEM das clausulas e a regra, nao um detalhe de escrita: o teste de NULL
-- vem antes do teste de saldo porque minimo ausente nao alerta nem com saldo
-- negativo, e o teste de saldo vem antes do de minimo zero porque zerar e
-- exatamente o que o minimo zero quer avisar.
-- A terceira clausula nao e redundante com o ELSE: com `p_min = 0`,
-- `p_min * 1.2` tambem e zero, entao saldo 5 com minimo 0 nao casa com
-- nenhuma das comparacoes seguintes e cairia no ELSE por acidente.

CREATE OR REPLACE FUNCTION public.fn_stock_state(
    p_stock integer,
    p_min   integer
) RETURNS public.stock_state
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_min IS NULL             THEN 'NORMAL'::public.stock_state
        WHEN COALESCE(p_stock, 0) <= 0 THEN 'CRITICO'::public.stock_state
        WHEN p_min = 0                 THEN 'NORMAL'::public.stock_state
        WHEN p_stock <= p_min          THEN 'BAIXO'::public.stock_state
        WHEN p_stock <  p_min * 1.2    THEN 'ATENCAO'::public.stock_state
        ELSE                                'NORMAL'::public.stock_state
    END;
$$;

-- 3. a escrita
-- Exigencia de `p_min` nao nulo. NULL vira o modo legitimo de LIMPAR o
-- minimo: sem ele nao haveria como desfazer uma configuracao, so zeraria.

CREATE OR REPLACE FUNCTION public.fn_set_min_stock(
    p_product_id uuid,
    p_min        integer
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
BEGIN
    IF p_min < 0 THEN
        RAISE EXCEPTION 'Estoque minimo nao pode ser negativo (recebido: %)', p_min
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT company_id INTO v_company FROM public.products WHERE id = p_product_id;

    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Produto nao encontrado ou sem permissao' USING ERRCODE = 'insufficient_privilege';
    END IF;

    INSERT INTO public.product_stock (product_id, min_quantity)
    VALUES (p_product_id, p_min)
    ON CONFLICT (product_id)
    DO UPDATE SET min_quantity = EXCLUDED.min_quantity;
END;
$$;

-- 4. as visoes
-- Os dois COALESCE sao removidos: o NULL e informacao, nao ausencia.

CREATE OR REPLACE VIEW public.vw_stock_situation
WITH (security_invoker = true) AS
SELECT
    p.company_id,
    p.id AS product_id,
    p.name AS product_name,
    p.stock AS current_balance,
    ps.min_quantity AS min_quantity,
    public.fn_stock_state(p.stock, ps.min_quantity) AS state
FROM public.products p
LEFT JOIN public.product_stock ps ON ps.product_id = p.id
WHERE p.active;

CREATE OR REPLACE VIEW public.vw_stock_alerts
WITH (security_invoker = true) AS
SELECT
    s.company_id,
    s.product_id,
    s.product_name,
    s.current_balance,
    s.min_quantity,
    s.state
FROM public.vw_stock_situation s
WHERE s.min_quantity IS NOT NULL
  AND s.current_balance <= s.min_quantity;

GRANT SELECT ON public.vw_stock_situation, public.vw_stock_alerts
  TO app_backend, authenticated;

DO $$
DECLARE v_missing text;
BEGIN
  SELECT string_agg(col, ', ')
    INTO v_missing
    FROM (VALUES ('current_balance'), ('min_quantity'), ('state')) AS t(col)
   WHERE NOT EXISTS (
         SELECT 1 FROM information_schema.columns c
          WHERE c.table_schema = 'public'
            AND c.table_name = 'vw_stock_alerts'
            AND c.column_name = col
   );
  IF v_missing IS NOT NULL THEN
    RAISE EXCEPTION 'vw_stock_alerts missing required columns: %', v_missing;
  END IF;
END $$;
