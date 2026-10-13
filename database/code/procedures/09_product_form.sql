-- Uma transação por formulário: nenhum produto parcialmente salvo.
CREATE OR REPLACE FUNCTION public.fn_save_product(
    p_company_id uuid, p_product_id uuid, p_data jsonb
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid := p_product_id;
    v_company uuid;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para salvar produtos' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_data IS NULL OR COALESCE(btrim(p_data->>'code'), '') = '' THEN
        RAISE EXCEPTION 'Identificador é obrigatório' USING ERRCODE = 'check_violation';
    END IF;
    IF (p_data->>'stock')::integer < 0 THEN
        RAISE EXCEPTION 'Estoque não pode ser negativo' USING ERRCODE = 'check_violation';
    END IF;
    IF v_id IS NULL THEN
        v_id := public.fn_create_products(
            p_company_id => p_company_id, p_barcode => p_data->>'code',
            p_name => p_data->>'name', p_sell_price => (p_data->>'sale_price')::numeric,
            p_buy_price => (p_data->>'cost')::numeric, p_unit => (p_data->>'unit')::public.unit_enum,
            p_stock => (p_data->>'stock')::integer, p_item_category => p_data->>'category');
    ELSE
        SELECT company_id INTO v_company FROM public.products
         WHERE id = v_id FOR UPDATE;
        IF v_company IS DISTINCT FROM p_company_id THEN
            RAISE EXCEPTION 'Produto não encontrado ou sem permissão' USING ERRCODE = 'insufficient_privilege';
        END IF;
        PERFORM public.fn_update_products(
            p_product_id => v_id, p_barcode => p_data->>'code', p_name => p_data->>'name',
            p_sell_price => (p_data->>'sale_price')::numeric, p_buy_price => (p_data->>'cost')::numeric,
            p_unit => (p_data->>'unit')::public.unit_enum, p_stock => (p_data->>'stock')::integer,
            p_item_category => p_data->>'category');
    END IF;
    PERFORM public.fn_set_product_supplier(v_id, (p_data->>'supplier_id')::uuid);
    PERFORM public.fn_set_min_stock(v_id, (p_data->>'minimum_stock')::integer);
    PERFORM public.fn_set_product_active(v_id, COALESCE((p_data->>'active')::boolean, true));
    UPDATE public.products SET
        description = COALESCE(p_data->>'description', ''), ncm = COALESCE(p_data->>'ncm', ''),
        ean = COALESCE(p_data->>'ean', ''), location = COALESCE(p_data->>'location', ''),
        low_stock_alert = COALESCE((p_data->>'low_stock_alert')::boolean, true),
        image_data = COALESCE(p_data->>'image_data', '')
    WHERE id = v_id;
    RETURN v_id;
END;
$$;
