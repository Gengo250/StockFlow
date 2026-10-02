CREATE OR REPLACE FUNCTION public.fn_set_min_stock(
    p_product_id uuid,
    p_min        integer
) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF p_min IS NULL THEN
        RAISE EXCEPTION 'Estoque mínimo é obrigatório';
    END IF;

    IF p_min < 0 THEN
        RAISE EXCEPTION 'Estoque mínimo não pode ser negativo (recebido: %)', p_min
            USING ERRCODE = 'check_violation';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM public.products WHERE id = p_product_id) THEN
        RAISE EXCEPTION 'Produto % não encontrado', p_product_id;
    END IF;

    INSERT INTO public.product_stock (product_id, min_quantity, updated_on)
    VALUES (p_product_id, p_min, now())
    ON CONFLICT (product_id)
    DO UPDATE SET min_quantity = EXCLUDED.min_quantity,
                  updated_on   = now();
END;
$$;