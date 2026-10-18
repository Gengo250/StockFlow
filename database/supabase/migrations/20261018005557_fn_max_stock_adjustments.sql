
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




--  Configura o teto global da empresa
CREATE OR REPLACE FUNCTION public.fn_set_company_max_stock_limit(
    p_company_id uuid,
    p_limit integer
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    -- Validação: O limite não pode ser negativo
    IF p_limit IS NULL OR p_limit < 0 THEN
    RAISE EXCEPTION 'O limite máximo de estoque deve ser um número maior ou igual a zero'
        USING ERRCODE = 'check_violation';
    END IF;

    -- Validação de Permissão
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Apenas administradores podem alterar o teto global'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF EXISTS (
    SELECT 1 FROM public.product_stock ps
    JOIN public.products p ON p.id = ps.product_id
    WHERE p.company_id = p_company_id AND ps.max_quantity > p_limit
) THEN
    RAISE EXCEPTION 'Não é possível definir o teto para %, pois existem produtos com estoque máximo superior', p_limit
        USING ERRCODE = 'check_violation';
END IF;

    UPDATE public.company SET max_stock_limit = p_limit WHERE id = p_company_id;
END;
$$;



CREATE OR REPLACE FUNCTION public.fn_get_effective_max_stock(p_product_id uuid)
RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    SELECT COALESCE(ps.max_quantity, c.max_stock_limit)
    FROM public.products p
    JOIN public.company c ON c.id = p.company_id
    LEFT JOIN public.product_stock ps ON ps.product_id = p.id
    WHERE p.id = p_product_id;
END;
$$;