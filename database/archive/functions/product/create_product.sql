CREATE OR REPLACE FUNCTION public.fn_create_category(
    p_company_id uuid,
    p_name       text
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id   uuid;
    v_name text := btrim(COALESCE(p_name, ''));
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para cadastrar categorias' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF v_name = '' THEN
        RAISE EXCEPTION 'Nome da categoria é obrigatório' USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM public.categories WHERE company_id = p_company_id AND lower(name) = lower(v_name)) THEN
        RAISE EXCEPTION 'Categoria "%" já existe', v_name USING ERRCODE = 'unique_violation';
    END IF;

    INSERT INTO public.categories (company_id, name) VALUES (p_company_id, v_name) RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_product(
    p_company_id  uuid,
    p_barcode     text,
    p_name        text,
    p_sell_price  numeric,
    p_unit        integer,                
    p_buy_price   numeric DEFAULT NULL,
    p_stock       integer DEFAULT 0,
    p_category_id uuid    DEFAULT NULL     
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id      uuid;
    v_barcode text := NULLIF(btrim(p_barcode), '');
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para cadastrar produtos' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_unit IS NULL THEN
        RAISE EXCEPTION 'Unidade é obrigatória' USING ERRCODE = 'not_null_violation';
    END IF;
    IF p_category_id IS NOT NULL AND NOT EXISTS (
           SELECT 1 FROM public.categories WHERE id = p_category_id AND company_id = p_company_id) THEN
        RAISE EXCEPTION 'Categoria não encontrada nesta empresa' USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO public.products (company_id, barcode, name, buy_price, sell_price, unit, stock, item_category)
    VALUES (p_company_id, v_barcode, btrim(p_name), p_buy_price, p_sell_price,
            p_unit, COALESCE(p_stock, 0), p_category_id)
    RETURNING id INTO v_id;

    RETURN v_id;    
END;
$$;


CREATE OR REPLACE FUNCTION public.fn_set_product_active(
    p_product_id uuid,
    p_active     boolean
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
BEGIN
    SELECT company_id INTO v_company FROM public.products WHERE id = p_product_id;
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Produto não encontrado ou sem permissão' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_active IS NULL THEN
        RAISE EXCEPTION 'p_active é obrigatório' USING ERRCODE = 'not_null_violation';
    END IF;

    UPDATE public.products SET active = p_active WHERE id = p_product_id;
END;
$$;