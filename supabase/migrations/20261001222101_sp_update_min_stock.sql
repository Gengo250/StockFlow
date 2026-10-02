CREATE OR REPLACE PROCEDURE public.sp_update_min_stock(p_items jsonb)
LANGUAGE plpgsql AS $$
DECLARE
    v_item jsonb;
BEGIN
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        PERFORM public.fn_set_min_stock(
            (v_item->>'product_id')::uuid,
            (v_item->>'min')::int
        );
    END LOOP;
END;
$$;