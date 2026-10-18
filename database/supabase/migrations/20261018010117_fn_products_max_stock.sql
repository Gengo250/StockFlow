
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
  v_company_limit integer;
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

  SELECT max_stock_limit INTO v_company_limit FROM public.company WHERE id = p_company_id;
  IF COALESCE(p_stock, 0) > v_company_limit THEN
    RAISE EXCEPTION 'O estoque inicial informado (%) excede o limite máximo permitido pela empresa (%)',
        p_stock, v_company_limit USING ERRCODE = 'check_violation';
  END IF;

  -- Nasce com saldo zero; o saldo informado vira a primeira movimentação.
  INSERT INTO public.products (
    company_id, barcode, name, buy_price, sell_price, unit, stock, item_category,
    created_by
  )
  VALUES (
    p_company_id, p_barcode, p_name, p_buy_price, p_sell_price, p_unit, 0, v_category_id,
    public.fn_current_user_id()
  )
  RETURNING id into v_new_id;




  IF COALESCE(p_stock, 0) > 0 THEN
    PERFORM public.fn_register_movement(
      p_company_id, v_new_id, 'ENTRADA', p_stock, 'Saldo inicial do cadastro', true);
  END IF;

  RETURN v_new_id;
END;
$$;


CREATE OR REPLACE FUNCTION public.fn_update_products (
  p_product_id    UUID,
  p_barcode       TEXT              DEFAULT NULL,
  p_name          TEXT              DEFAULT NULL,
  p_sell_price    NUMERIC (10, 2)   DEFAULT NULL,
  p_buy_price     NUMERIC (10, 2)   DEFAULT NULL,
  p_unit          public.unit_enum  DEFAULT NULL,
  p_stock         INTEGER           DEFAULT NULL,
  p_item_category TEXT              DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
  v_company     UUID;
  v_category_id UUID;
  v_atual       INTEGER;
  v_delta       INTEGER;
  v_max         INTEGER;
BEGIN
  SELECT company_id, stock INTO v_company, v_atual
    FROM public.products
   WHERE id = p_product_id FOR UPDATE;

  IF v_company IS NULL
     OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
    RAISE EXCEPTION 'Produto não encontrado ou sem permissão'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  IF p_item_category IS NOT NULL THEN
    SELECT id INTO v_category_id
      FROM public.categories
     WHERE company_id = v_company AND name = p_item_category;

    IF v_category_id IS NULL THEN
      RAISE EXCEPTION 'Item category doesnt exist' USING ERRCODE = 'foreign_key_violation';
    END IF;
  END IF;

  -- `stock` SAI do UPDATE: quem muda saldo é movimentação.
  UPDATE public.products
     SET barcode       = COALESCE(p_barcode, barcode),
         name          = COALESCE(p_name, name),
         buy_price     = COALESCE(p_buy_price, buy_price),
         sell_price    = COALESCE(p_sell_price, sell_price),
         unit          = COALESCE(p_unit, unit),
         item_category = COALESCE(v_category_id, item_category)
   WHERE id = p_product_id;

  -- Saldo informado vira a movimentação que falta para chegar nele. O
  -- formulário manda a tela inteira, então "igual ao atual" é o caso comum e
  -- não pode gerar movimentação de quantidade zero.
  -- Em fn_update_products (05_catalog.sql):
  IF p_stock IS NOT NULL THEN
    v_max := public.fn_get_effective_max_stock(p_product_id);
    IF v_max IS NOT NULL AND p_stock > v_max THEN
        RAISE EXCEPTION 'O novo estoque (%) ultrapassa o estoque máximo permitido (%)',
            p_stock, v_max USING ERRCODE = 'check_violation';
    END IF;
        v_delta := p_stock - v_atual;
    IF v_delta > 0 THEN
      PERFORM public.fn_register_movement(
        v_company, p_product_id, 'ENTRADA', v_delta, 'Ajuste pelo cadastro', true);
    ELSIF v_delta < 0 THEN
      PERFORM public.fn_register_movement(
        v_company, p_product_id, 'SAIDA', -v_delta, 'Ajuste pelo cadastro', true);
    END IF;
  END IF;
    

END;
$$;
