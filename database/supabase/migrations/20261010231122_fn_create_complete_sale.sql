CREATE OR REPLACE FUNCTION public.fn_create_complete_sale(
    p_company_id        uuid,
    p_register_id       uuid,
    p_client_id         uuid DEFAULT NULL,
    p_customer_name     text DEFAULT 'Consumidor',
    p_customer_document text DEFAULT NULL,
    p_items             jsonb DEFAULT '[]'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_sale_id    uuid;
    v_item       jsonb;
    v_prod_price numeric(10,2);
    v_prod_name  text;
    v_prod_code  text;
    v_total_sale numeric(10,2) := 0.00;
BEGIN
  INSERT INTO public.sales (
        company_id,
        register_id,
        client_id,
        customer_name,
        customer_document,
        status,
        total
    ) VALUES (
        p_company_id,
        p_register_id,
        p_client_id,
        p_customer_name,
        p_customer_document,
        'PENDING',
        0.00
    )
  RETURNING id INTO v_sale_id;

  FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
      SELECT name, price, sku
          INTO v_prod_name, v_prod_price, v_prod_code
          FROM public.products
         WHERE id = (v_item->>'product_id')::uuid
           AND company_id = p_company_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Produto não encontrado: %', v_item->>'product_id';
        END IF;
        
        INSERT INTO public.sale_items (
            company_id,
            sale_id,
            product_id,
            product_name,
            product_code,
            quantity,
            unit_price
        ) VALUES (
            p_company_id,
            v_sale_id,
            (v_item->>'product_id')::uuid,
            v_prod_name,
            COALESCE(v_prod_code, ''),
            (v_item->>'quantity')::numeric,
            v_prod_price
        );

        v_total_sale := v_total_sale + ((v_item->>'quantity')::numeric * v_prod_price);
    END LOOP;

    UPDATE public.sales
       SET total = v_total_sale,
           status = 'COMPLETE'
     WHERE id = v_sale_id;

    RETURN v_sale_id;
END;
$$;
