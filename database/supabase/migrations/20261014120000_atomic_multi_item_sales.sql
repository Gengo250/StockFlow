-- Desktop multi-item sales share US10's header/items and completion trigger.
-- The stock exit is created only by fn_process_sale_completion.

CREATE OR REPLACE FUNCTION public.fn_process_sale_completion()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_item    RECORD;
    v_balance integer;
BEGIN
    INSERT INTO public.sales_log (company_id, sale_id, created_by)
    VALUES (NEW.company_id, NEW.id, NEW.created_by);

    FOR v_item IN
        SELECT product_id, product_name, quantity
          FROM public.sale_items
         WHERE sale_id = NEW.id AND product_id IS NOT NULL
         ORDER BY product_id, id
    LOOP
        v_balance := public.fn_confirmed_balance(v_item.product_id);
        IF v_balance < v_item.quantity THEN
            RAISE EXCEPTION
                'Estoque insuficiente para % (disponível: %, vendido: %)',
                v_item.product_name, v_balance, v_item.quantity
                USING ERRCODE = 'check_violation';
        END IF;

        INSERT INTO public.stock_movements (
            company_id, product_id, sale_id, kind, quantity, status,
            note, created_by, confirmed_on
        ) VALUES (
            NEW.company_id, v_item.product_id, NEW.id, 'SAIDA',
            v_item.quantity, 'CONFIRMADA',
            'SAIDA_VENDA - venda ' || NEW.id::text,
            NEW.created_by, now()
        );
    END LOOP;

    RETURN NULL;
END;
$$;

DROP FUNCTION IF EXISTS public.fn_register_sale(uuid, uuid, jsonb);
CREATE OR REPLACE FUNCTION public.fn_register_sale(
    p_company_id uuid,
    p_client_id uuid,
    p_items jsonb,
    p_payment_method public.payment_method DEFAULT 'DINHEIRO',
    p_discount numeric DEFAULT 0
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
    v_client_name text;
    v_item record;
    v_product record;
    v_line record;
    v_gross_total numeric := 0;
    v_total numeric;
    v_created_on timestamptz;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para registrar vendas nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array'
       OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'A venda deve ter pelo menos um item'
            USING ERRCODE = 'check_violation';
    END IF;
    IF p_payment_method IS NULL
       OR p_discount IS NULL OR p_discount < 0
       OR p_discount::text IN ('NaN', 'Infinity', '-Infinity') THEN
        RAISE EXCEPTION 'Forma de pagamento ou desconto inválido'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM jsonb_array_elements(p_items) AS entry(value)
         WHERE jsonb_typeof(entry.value) <> 'object'
            OR COALESCE(jsonb_typeof(entry.value->'product_code'), 'null') <> 'string'
            OR COALESCE(jsonb_typeof(entry.value->'quantity'), 'null') <> 'number'
            OR COALESCE(entry.value->>'product_code', '') = ''
            OR COALESCE(entry.value->>'quantity', '') !~ '^[1-9][0-9]*$'
    ) THEN
        RAISE EXCEPTION 'Produto e quantidade inteira positiva são obrigatórios'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT name INTO v_client_name
      FROM public.clients
     WHERE id = p_client_id AND company_id = p_company_id AND active
     FOR SHARE;
    IF v_client_name IS NULL THEN
        RAISE EXCEPTION 'Cliente não encontrado, inativo ou sem permissão'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    FOR v_item IN
        SELECT entry.value->>'product_code' AS product_code,
               sum((entry.value->>'quantity')::numeric) AS quantity
          FROM jsonb_array_elements(p_items) AS entry(value)
         GROUP BY entry.value->>'product_code'
         ORDER BY entry.value->>'product_code'
    LOOP
        SELECT id, name, sell_price, stock
          INTO v_product
          FROM public.products
         WHERE company_id = p_company_id
           AND barcode = v_item.product_code
           AND active
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Produto % não encontrado, inativo ou sem permissão',
                v_item.product_code
                USING ERRCODE = 'foreign_key_violation';
        END IF;
        IF v_item.quantity > 2147483647 OR v_product.stock < v_item.quantity THEN
            RAISE EXCEPTION
                'Estoque insuficiente para o produto %: solicitado %, disponível %',
                v_item.product_code, v_item.quantity, v_product.stock
                USING ERRCODE = 'check_violation';
        END IF;
        v_gross_total := v_gross_total + v_product.sell_price * v_item.quantity;
    END LOOP;

    IF p_discount > v_gross_total OR v_gross_total >= 100000000 THEN
        RAISE EXCEPTION 'Desconto ou total da venda inválido'
            USING ERRCODE = 'check_violation';
    END IF;
    v_total := v_gross_total - p_discount;

    INSERT INTO public.sales (
        company_id, client_id, client_name, payment_method, discount,
        total, created_by
    ) VALUES (
        p_company_id, p_client_id, v_client_name, p_payment_method, p_discount,
        v_total, public.fn_current_user_id()
    )
    RETURNING id, created_on INTO v_id, v_created_on;

    FOR v_line IN
        SELECT entry.value->>'product_code' AS product_code,
               (entry.value->>'quantity')::integer AS quantity
          FROM jsonb_array_elements(p_items) AS entry(value)
    LOOP
        SELECT id, name, barcode, sell_price
          INTO v_product
          FROM public.products
         WHERE company_id = p_company_id
           AND barcode = v_line.product_code
           AND active;

        INSERT INTO public.sale_items (
            company_id, sale_id, product_id, product_name, product_code,
            quantity, unit_price
        ) VALUES (
            p_company_id, v_id, v_product.id, v_product.name,
            v_product.barcode, v_line.quantity, v_product.sell_price
        );
    END LOOP;

    UPDATE public.sales SET status = 'CONCLUIDA' WHERE id = v_id;
    RETURN jsonb_build_object(
        'id', v_id,
        'cliente', v_client_name,
        'total', v_total,
        'created_on', v_created_on,
        'items', (
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'product_code', si.product_code,
                'product_name', si.product_name,
                'quantity', si.quantity,
                'unit_price', si.unit_price,
                'subtotal', si.subtotal
            ) ORDER BY si.created_on, si.id), '[]'::jsonb)
              FROM public.sale_items si
             WHERE si.sale_id = v_id
        )
    );
END;
$$;

REVOKE ALL ON FUNCTION public.fn_register_sale(
    uuid, uuid, jsonb, public.payment_method, numeric
) FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_register_sale(
    uuid, uuid, jsonb, public.payment_method, numeric
) TO app_backend, authenticated;
