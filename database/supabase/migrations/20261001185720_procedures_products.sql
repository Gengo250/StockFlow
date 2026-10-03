-- ==========================================
-- SOURCE: procedures/products.sql
-- ==========================================

-- As versões sem company_id violavam o NOT NULL de categories/products desde
-- que o schema virou multi-tenant; removidas para não sobrarem inutilizáveis.
DROP FUNCTION IF EXISTS create_categories(TEXT);
DROP FUNCTION IF EXISTS create_products(TEXT, TEXT, NUMERIC, NUMERIC, unit_enum, INTEGER, TEXT);

CREATE OR REPLACE FUNCTION public.fn_create_categories (
  p_company_id UUID,
  p_name       TEXT
)
RETURNS UUID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
  v_new_id UUID;
BEGIN
  IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
    RAISE EXCEPTION 'Sem permissão para cadastrar categorias nesta empresa'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  -- categories é UNIQUE (company_id, name): o mesmo nome pode existir em
  -- outra empresa, então a checagem precisa ser escopada.
  IF EXISTS (
    SELECT 1 FROM public.categories
     WHERE company_id = p_company_id AND name = p_name
  ) THEN
    RAISE EXCEPTION 'Category already exists' USING ERRCODE = 'unique_violation';
  END IF;

  INSERT INTO public.categories (
    company_id,
    name
  )
  VALUES (
    p_company_id,
    p_name
  )
  RETURNING id INTO v_new_id;

  RETURN v_new_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_products (
  p_company_id    UUID,
  p_barcode       TEXT,
  p_name          TEXT,
  p_sell_price    NUMERIC (10, 2),
  p_buy_price     NUMERIC (10, 2)   DEFAULT NULL,
  p_unit          public.unit_enum  DEFAULT 'UN',
  p_stock         INTEGER           DEFAULT 0,
  p_item_category TEXT              DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
  v_new_id      UUID;
  v_category_id UUID;
BEGIN
  IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
    RAISE EXCEPTION 'Sem permissão para cadastrar produtos nesta empresa'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  IF p_item_category IS NOT NULL THEN
    SELECT id INTO v_category_id
      FROM public.categories
     WHERE company_id = p_company_id AND name = p_item_category;

    IF v_category_id IS NULL THEN
      RAISE EXCEPTION 'Item category doesnt exist' USING ERRCODE = 'foreign_key_violation';

    END IF;
  END IF;

  INSERT INTO public.products (
    company_id,
    barcode,
    name,
    buy_price,
    sell_price,
    unit,
    stock,
    item_category
  )
  VALUES (
    p_company_id,
    p_barcode,
    p_name,
    p_buy_price,
    p_sell_price,
    p_unit,
    p_stock,
    v_category_id
  )
  RETURNING id into v_new_id;

  RETURN v_new_id;
END;
$$;
