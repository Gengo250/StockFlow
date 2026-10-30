-- Limites e registro atômico de descontos (US22), conciliados com a main.

CREATE OR REPLACE FUNCTION public.fn_get_sale_discount_limits(
    p_company_id uuid
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_limit numeric;
BEGIN
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Empresa não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT limit_percent INTO v_limit
      FROM public.sale_discount_limits
     WHERE company_id = p_company_id AND role = 'SELLER';
    RETURN jsonb_build_object(
        'SELLER', COALESCE(v_limit, 10.00),
        'ADMIN', NULL
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_set_sale_discount_limit(
    p_company_id uuid,
    p_role public.user_role,
    p_limit_percent numeric
) RETURNS numeric
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Somente ADMIN pode alterar limites de desconto'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_role IS NULL OR p_role <> 'SELLER' OR p_limit_percent IS NULL
       OR p_limit_percent < 0 OR p_limit_percent > 100
       OR p_limit_percent::text IN ('NaN', 'Infinity', '-Infinity')
       OR p_limit_percent <> round(p_limit_percent, 2) THEN
        RAISE EXCEPTION 'Perfil ou limite percentual inválido'
            USING ERRCODE = 'check_violation';
    END IF;
    INSERT INTO public.sale_discount_limits (
        company_id, role, limit_percent, updated_by, updated_on
    ) VALUES (
        p_company_id, p_role, p_limit_percent, v_actor, now()
    )
    ON CONFLICT (company_id, role) DO UPDATE
       SET limit_percent = EXCLUDED.limit_percent,
           updated_by = EXCLUDED.updated_by,
           updated_on = EXCLUDED.updated_on;
    RETURN p_limit_percent;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_register_sale_with_discounts(
    p_company_id uuid,
    p_client_id uuid,
    p_items jsonb,
    p_payment_method public.payment_method,
    p_sale_discount_type text,
    p_sale_discount_value numeric,
    p_seller_id uuid
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
    v_seller uuid;
    v_seller_role public.user_role;
    v_authorizer uuid;
    v_authorizer_name text;
    v_limit numeric;
    v_id uuid;
    v_client_name text;
    v_item record;
    v_product record;
    v_product_ids uuid[] := ARRAY[]::uuid[];
    v_product_codes text[] := ARRAY[]::text[];
    v_product_names text[] := ARRAY[]::text[];
    v_unit_prices numeric[] := ARRAY[]::numeric[];
    v_item_discounts numeric[] := ARRAY[]::numeric[];
    v_gross_total numeric := 0;
    v_item_discount_total numeric := 0;
    v_sale_discount numeric := 0;
    v_discount_total numeric := 0;
    v_discount_percent numeric := 0;
    v_remaining numeric := 0;
    v_total numeric := 0;
    v_item_subtotal numeric;
    v_item_discount numeric;
    v_item_type text;
    v_item_value numeric;
    v_sale_type text := upper(btrim(COALESCE(p_sale_discount_type, '')));
    v_sale_value numeric := p_sale_discount_value;
    v_index integer;
    v_line record;
BEGIN
    IF NOT public.fn_has_role(
        p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]
    ) THEN
        RAISE EXCEPTION 'Sem permissão para registrar vendas nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_payment_method IS NULL OR p_items IS NULL
       OR jsonb_typeof(p_items) <> 'array'
       OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'Pagamento e pelo menos um item são obrigatórios'
            USING ERRCODE = 'check_violation';
    END IF;
    v_seller := COALESCE(p_seller_id, v_actor);
    IF v_seller <> v_actor
       AND NOT public.fn_has_role(
           p_company_id, ARRAY['ADMIN']::public.user_role[]
       ) THEN
        RAISE EXCEPTION 'Vendedor informado não corresponde ao usuário autenticado'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT cu.role INTO v_seller_role
      FROM public.company_users cu
      JOIN public.company c ON c.id = cu.company_id
     WHERE cu.company_id = p_company_id
       AND cu.user_account_id = v_seller
       AND cu.active AND c.active;
    IF NOT FOUND OR v_seller_role NOT IN ('ADMIN', 'SELLER') THEN
        RAISE EXCEPTION 'Vendedor não encontrado ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM jsonb_array_elements(p_items) AS entry(value)
         WHERE jsonb_typeof(entry.value) <> 'object'
            OR COALESCE(jsonb_typeof(entry.value->'product_code'), 'null') <> 'string'
            OR COALESCE(jsonb_typeof(entry.value->'quantity'), 'null') <> 'number'
            OR COALESCE(entry.value->>'product_code', '') = ''
            OR COALESCE(entry.value->>'quantity', '') !~ '^[1-9][0-9]*$'
            OR upper(COALESCE(entry.value->>'discount_type', 'FIXED'))
               NOT IN ('FIXED', 'PERCENTAGE')
            OR COALESCE(entry.value->>'discount_value', '0')
               !~ '^[0-9]+(\.[0-9]{1,2})?$'
    ) THEN
        RAISE EXCEPTION 'Produto, quantidade ou desconto de item inválido'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM jsonb_array_elements(p_items) AS entry(value)
         WHERE (entry.value->>'quantity')::numeric > 1000000
            OR (COALESCE(entry.value->>'discount_value', '0'))::numeric >= 100000000
    ) THEN
        RAISE EXCEPTION 'Quantidade ou desconto de item acima do limite'
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_sale_type NOT IN ('FIXED', 'PERCENTAGE')
       OR v_sale_value IS NULL OR v_sale_value < 0
       OR v_sale_value >= 100000000
       OR v_sale_value::text IN ('NaN', 'Infinity', '-Infinity')
       OR v_sale_value <> round(v_sale_value, 2)
       OR (v_sale_type = 'PERCENTAGE' AND v_sale_value > 100) THEN
        RAISE EXCEPTION 'Desconto total inválido'
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
        SELECT id, name, barcode, sell_price, stock
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
        v_product_ids := array_append(v_product_ids, v_product.id);
        v_product_codes := array_append(v_product_codes, v_product.barcode);
        v_product_names := array_append(v_product_names, v_product.name);
        v_unit_prices := array_append(v_unit_prices, v_product.sell_price);
        v_gross_total := v_gross_total + v_product.sell_price * v_item.quantity;
    END LOOP;
    IF v_gross_total >= 100000000 THEN
        RAISE EXCEPTION 'Total da venda acima do limite permitido'
            USING ERRCODE = 'check_violation';
    END IF;
    FOR v_item IN
        SELECT entry.value->>'product_code' AS product_code,
               (entry.value->>'quantity')::integer AS quantity,
               upper(COALESCE(entry.value->>'discount_type', 'FIXED')) AS discount_type,
               COALESCE(entry.value->>'discount_value', '0')::numeric AS discount_value,
               entry.ordinality::integer AS line_number
          FROM jsonb_array_elements(p_items) WITH ORDINALITY AS entry(value, ordinality)
         ORDER BY entry.ordinality
    LOOP
        v_index := array_position(v_product_codes, v_item.product_code);
        v_item_subtotal := v_unit_prices[v_index] * v_item.quantity;
        v_item_type := v_item.discount_type;
        v_item_value := v_item.discount_value;
        IF v_item_type = 'PERCENTAGE' THEN
            IF v_item_value > 100 THEN
                RAISE EXCEPTION 'Desconto percentual de item acima de 100%%'
                    USING ERRCODE = 'check_violation';
            END IF;
            v_item_discount := round(v_item_subtotal * v_item_value / 100, 2);
        ELSE
            v_item_discount := v_item_value;
        END IF;
        IF v_item_discount > v_item_subtotal THEN
            RAISE EXCEPTION 'Desconto maior que o subtotal do item %',
                v_item.product_code
                USING ERRCODE = 'check_violation';
        END IF;
        v_item_discounts := array_append(v_item_discounts, v_item_discount);
        v_item_discount_total := v_item_discount_total + v_item_discount;
    END LOOP;
    v_remaining := v_gross_total - v_item_discount_total;
    IF v_sale_type = 'PERCENTAGE' THEN
        v_sale_discount := round(v_remaining * v_sale_value / 100, 2);
    ELSE
        v_sale_discount := v_sale_value;
    END IF;
    IF v_sale_discount > v_remaining THEN
        RAISE EXCEPTION 'Desconto maior que o total restante da venda'
            USING ERRCODE = 'check_violation';
    END IF;
    v_discount_total := v_item_discount_total + v_sale_discount;
    v_total := v_gross_total - v_discount_total;
    IF v_gross_total > 0 THEN
        v_discount_percent := v_discount_total * 100 / v_gross_total;
    END IF;
    IF v_seller_role = 'SELLER' THEN
        SELECT COALESCE((
            SELECT sdl.limit_percent
              FROM public.sale_discount_limits sdl
             WHERE sdl.company_id = p_company_id AND sdl.role = 'SELLER'
        ), 10.00) INTO v_limit;
        IF v_discount_percent > v_limit THEN
            IF NOT public.fn_has_role(
                p_company_id, ARRAY['ADMIN']::public.user_role[]
            ) THEN
                RAISE EXCEPTION
                    'Desconto acima do limite de %%%: aprovação de ADMIN necessária',
                    v_limit
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            v_authorizer := v_actor;
            SELECT name INTO v_authorizer_name
              FROM public.user_accounts WHERE id = v_authorizer;
        END IF;
    END IF;
    INSERT INTO public.sales (
        company_id, client_id, client_name, payment_method, discount, total,
        sale_discount_type, sale_discount_value, created_by,
        discount_applied_by, discount_authorized_by
    ) VALUES (
        p_company_id, p_client_id, v_client_name, p_payment_method,
        v_discount_total, v_total, v_sale_type, v_sale_value, v_seller,
        CASE WHEN v_discount_total > 0 THEN v_seller ELSE NULL END,
        v_authorizer
    )
    RETURNING id INTO v_id;
    FOR v_line IN
        SELECT entry.value->>'product_code' AS product_code,
               (entry.value->>'quantity')::integer AS quantity,
               upper(COALESCE(entry.value->>'discount_type', 'FIXED')) AS discount_type,
               COALESCE(entry.value->>'discount_value', '0')::numeric AS discount_value,
               entry.ordinality::integer AS line_number
          FROM jsonb_array_elements(p_items) WITH ORDINALITY AS entry(value, ordinality)
         ORDER BY entry.ordinality
    LOOP
        v_index := array_position(v_product_codes, v_line.product_code);
        INSERT INTO public.sale_items (
            company_id, sale_id, product_id, product_name, product_code,
            quantity, unit_price, discount_type, discount_value, discount_amount
        ) VALUES (
            p_company_id, v_id, v_product_ids[v_index], v_product_names[v_index],
            v_product_codes[v_index], v_line.quantity, v_unit_prices[v_index],
            v_line.discount_type, v_line.discount_value,
            v_item_discounts[v_line.line_number]
        );
    END LOOP;
    UPDATE public.sales SET status = 'CONCLUIDA' WHERE id = v_id;
    RETURN jsonb_build_object(
        'id', v_id,
        'cliente', v_client_name,
        'total', v_total,
        'original_total', v_gross_total,
        'discount', v_discount_total,
        'sale_discount_type', v_sale_type,
        'sale_discount_value', v_sale_value,
        'created_on', (SELECT created_on FROM public.sales WHERE id = v_id),
        'seller_id', v_seller,
        'discount_applied_by', CASE
            WHEN v_discount_total > 0 THEN v_seller ELSE NULL END,
        'discount_authorized_by', v_authorizer,
        'discount_authorized_by_name', COALESCE(v_authorizer_name, ''),
        'items', (
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'product_code', si.product_code,
                'product_name', si.product_name,
                'quantity', si.quantity,
                'unit_price', si.unit_price,
                'subtotal', si.subtotal,
                'discount_type', si.discount_type,
                'discount_value', si.discount_value,
                'discount_amount', si.discount_amount,
                'final_subtotal', si.final_subtotal
            ) ORDER BY si.created_on, si.id), '[]'::jsonb)
              FROM public.sale_items si
             WHERE si.sale_id = v_id
        )
    );
END;
$$;

-- Mesma assinatura legada, agora passando pela regra de limite da US22.
DROP FUNCTION IF EXISTS public.fn_register_sale(
    uuid, uuid, jsonb, public.payment_method, numeric
);
CREATE OR REPLACE FUNCTION public.fn_register_sale(
    p_company_id uuid,
    p_client_id uuid,
    p_items jsonb,
    p_payment_method public.payment_method DEFAULT 'DINHEIRO',
    p_discount numeric DEFAULT 0
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF NOT public.fn_has_role(
        p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]
    ) THEN
        RAISE EXCEPTION 'Sem permissão para registrar vendas nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN public.fn_register_sale_with_discounts(
        p_company_id,
        p_client_id,
        p_items,
        p_payment_method,
        'FIXED',
        p_discount,
        NULL
    );
END;
$$;
