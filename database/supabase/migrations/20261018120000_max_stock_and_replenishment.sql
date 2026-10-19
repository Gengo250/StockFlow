-- Migration para estoque máximo e sugestão de reposição (US - Sugestão de Reposição)

ALTER TABLE public.product_stock 
    ADD COLUMN IF NOT EXISTS max_quantity integer CHECK (max_quantity >= 0);

ALTER TABLE public.product_stock 
    DROP CONSTRAINT IF EXISTS chk_max_ge_min;

ALTER TABLE public.product_stock 
    ADD CONSTRAINT chk_max_ge_min 
    CHECK (max_quantity IS NULL OR min_quantity IS NULL OR max_quantity >= min_quantity);

CREATE OR REPLACE FUNCTION public.fn_set_max_stock(
    p_product_id uuid,
    p_max        integer
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_min integer;
    v_global_limit integer;
    v_current_stock integer;
BEGIN
    --  Validação de valor negativo
    IF p_max < 0 THEN
        RAISE EXCEPTION 'Estoque máximo não pode ser negativo (recebido: %)', p_max
            USING ERRCODE = 'check_violation';
    END IF;
    --  Verifica empresa e papel
    SELECT company_id INTO v_company FROM public.products WHERE id = p_product_id;
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Produto não encontrado ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    --Teto global (ou per‑company) -------------------------------------------------
    SELECT max_stock_limit INTO v_global_limit FROM public.company WHERE id = v_company;
    IF v_global_limit IS NOT NULL AND p_max > v_global_limit THEN
        RAISE EXCEPTION 'O estoque máximo (%) excede o teto da empresa (%)',
            p_max, v_global_limit USING ERRCODE = 'check_violation';
    END IF;
    -- Validação contra o estoque  mínimo
    SELECT min_quantity INTO v_min FROM public.product_stock WHERE product_id = p_product_id;
    IF p_max IS NOT NULL AND v_min IS NOT NULL AND p_max < v_min THEN
        RAISE EXCEPTION 'Estoque máximo (%s) não pode ser inferior ao mínimo (%s)',
            p_max, v_min USING ERRCODE = 'check_violation';
    END IF;
    -- Não pode ser menor que o saldo físico
    SELECT stock INTO v_current_stock FROM public.products WHERE id = p_product_id;
    IF p_max IS NOT NULL AND v_current_stock > p_max THEN
        RAISE EXCEPTION 'Estoque máximo (%) não pode ser menor que o saldo atual (%)',
            p_max, v_current_stock USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.product_stock (product_id, max_quantity, updated_on)
    VALUES (p_product_id, p_max, now())
    ON CONFLICT (product_id) DO UPDATE
       SET max_quantity = EXCLUDED.max_quantity,
           updated_on   = now();
END;
$$;

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
