CREATE OR REPLACE FUNCTION public.fn_set_min_stock(
    p_product_id uuid,
    p_min        integer
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
BEGIN
    IF p_min IS NULL THEN
        RAISE EXCEPTION 'Estoque mínimo é obrigatório' USING ERRCODE = 'not_null_violation';
    END IF;
    IF p_min < 0 THEN
        RAISE EXCEPTION 'Estoque mínimo não pode ser negativo (recebido: %)', p_min
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT company_id INTO v_company FROM public.products WHERE id = p_product_id;

    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Produto não encontrado ou sem permissão' USING ERRCODE = 'insufficient_privilege';
    END IF;

    INSERT INTO public.product_stock (product_id, min_quantity)
    VALUES (p_product_id, p_min)
    ON CONFLICT (product_id)
    DO UPDATE SET min_quantity = EXCLUDED.min_quantity;
END;
$$;