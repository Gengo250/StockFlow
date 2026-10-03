CREATE OR REPLACE FUNCTION public.fn_set_min_stock_batch(p_items jsonb)
RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_item jsonb;
    v_n    integer := 0;
BEGIN
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' THEN
        RAISE EXCEPTION 'p_items deve ser um array JSON' USING ERRCODE = 'invalid_parameter_value';
    END IF;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        PERFORM public.fn_set_min_stock((v_item->>'product_id')::uuid, (v_item->>'min')::int);
        v_n := v_n + 1;
    END LOOP;

    RETURN v_n;
END;
$$;
