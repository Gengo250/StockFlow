-- Limites e registro atômico de descontos (US22).

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

DROP FUNCTION IF EXISTS public.fn_register_sale_with_discounts(
    uuid, uuid, jsonb, public.payment_method, text, numeric, uuid
);
CREATE OR REPLACE FUNCTION public.fn_register_sale_with_discounts(
    p_company_id uuid,
    p_client_id uuid,
    p_items jsonb,
    p_payment_method public.payment_method,
    p_sale_discount_type text,
    p_sale_discount_value numeric,
    p_seller_id uuid,
    p_payments jsonb DEFAULT NULL
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
    v_primary_method public.payment_method := p_payment_method;
    v_non_cash_sum numeric := 0;
    v_cash_received_sum numeric := 0;
    v_has_cash boolean := false;
    v_cash_remaining numeric := 0;
    v_pay_entry record;
    v_pay_method public.payment_method;
    v_pay_received numeric;
    v_pay_applied numeric;
    v_pay_change numeric;
    v_change_total numeric := 0;
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

    IF p_payments IS NOT NULL THEN
        IF jsonb_typeof(p_payments) <> 'array' THEN
            RAISE EXCEPTION 'Lista de pagamentos inválida'
                USING ERRCODE = 'check_violation';
        END IF;
        IF v_total = 0 THEN
            IF jsonb_array_length(p_payments) > 0 THEN
                RAISE EXCEPTION 'Venda com total zerado não aceita pagamentos positivos'
                    USING ERRCODE = 'check_violation';
            END IF;
        ELSE
            IF jsonb_array_length(p_payments) = 0 THEN
                RAISE EXCEPTION 'Informe pelo menos uma forma de pagamento'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF EXISTS (
                SELECT 1
                  FROM jsonb_array_elements(p_payments) AS p(val)
                 WHERE jsonb_typeof(p.val) <> 'object'
                    OR upper(btrim(COALESCE(p.val->>'payment_method', '')))
                       NOT IN ('DINHEIRO', 'DEBITO', 'CREDITO', 'PIX', 'VALE', 'OUTRO')
                    OR COALESCE(
                           NULLIF(btrim(p.val->>'received_amount'), ''),
                           NULLIF(btrim(p.val->>'amount'), ''),
                           ''
                       ) !~ '^[0-9]+(\.[0-9]{1,2})?$'
            ) THEN
                RAISE EXCEPTION 'Forma ou valor de pagamento inválido'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF EXISTS (
                SELECT 1
                  FROM jsonb_array_elements(p_payments) AS p(val)
                 WHERE COALESCE(
                           NULLIF(btrim(p.val->>'received_amount'), ''),
                           NULLIF(btrim(p.val->>'amount'), '')
                       )::numeric <= 0
                    OR COALESCE(
                           NULLIF(btrim(p.val->>'received_amount'), ''),
                           NULLIF(btrim(p.val->>'amount'), '')
                       )::numeric >= 100000000
            ) THEN
                RAISE EXCEPTION 'O valor do pagamento deve ser maior que zero'
                    USING ERRCODE = 'check_violation';
            END IF;

            SELECT upper(btrim(p.val->>'payment_method'))::public.payment_method
              INTO v_primary_method
              FROM jsonb_array_elements(p_payments) WITH ORDINALITY AS p(val, ord)
             ORDER BY p.ord
             LIMIT 1;

            SELECT
                COALESCE(SUM(
                    COALESCE(
                        NULLIF(btrim(p.val->>'received_amount'), ''),
                        NULLIF(btrim(p.val->>'amount'), '')
                    )::numeric
                ) FILTER (WHERE upper(btrim(p.val->>'payment_method')) <> 'DINHEIRO'), 0),
                COALESCE(SUM(
                    COALESCE(
                        NULLIF(btrim(p.val->>'received_amount'), ''),
                        NULLIF(btrim(p.val->>'amount'), '')
                    )::numeric
                ) FILTER (WHERE upper(btrim(p.val->>'payment_method')) = 'DINHEIRO'), 0),
                COALESCE(BOOL_OR(upper(btrim(p.val->>'payment_method')) = 'DINHEIRO'), false)
              INTO v_non_cash_sum, v_cash_received_sum, v_has_cash
              FROM jsonb_array_elements(p_payments) AS p(val);

            IF v_non_cash_sum > v_total THEN
                RAISE EXCEPTION 'A soma dos pagamentos fora do dinheiro não pode exceder o total da venda'
                    USING ERRCODE = 'check_violation';
            END IF;
            v_cash_remaining := v_total - v_non_cash_sum;
            IF v_has_cash AND v_cash_remaining <= 0 THEN
                RAISE EXCEPTION 'O total da venda já foi coberto pelas demais formas de pagamento'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF (v_non_cash_sum + v_cash_received_sum) < v_total
               OR (NOT v_has_cash AND v_non_cash_sum <> v_total) THEN
                RAISE EXCEPTION 'A soma dos pagamentos deve ser igual ao total da venda'
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;
    END IF;

    INSERT INTO public.sales (
        company_id, client_id, client_name, payment_method, discount, total,
        sale_discount_type, sale_discount_value, created_by,
        discount_applied_by, discount_authorized_by
    ) VALUES (
        p_company_id, p_client_id, v_client_name, v_primary_method,
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

    IF p_payments IS NOT NULL AND v_total > 0 THEN
        FOR v_pay_entry IN
            SELECT upper(btrim(p.val->>'payment_method'))::public.payment_method AS method,
                   COALESCE(
                       NULLIF(btrim(p.val->>'received_amount'), ''),
                       NULLIF(btrim(p.val->>'amount'), '')
                   )::numeric AS received_amount
              FROM jsonb_array_elements(p_payments) WITH ORDINALITY AS p(val, ord)
             ORDER BY p.ord
        LOOP
            v_pay_method := v_pay_entry.method;
            v_pay_received := v_pay_entry.received_amount;
            IF v_pay_method <> 'DINHEIRO' THEN
                v_pay_applied := v_pay_received;
                v_pay_change := 0;
            ELSE
                IF v_cash_remaining <= 0 THEN
                    RAISE EXCEPTION 'Pagamento em dinheiro excedente: cada linha deve abater parte do total'
                        USING ERRCODE = 'check_violation';
                END IF;
                v_pay_applied := LEAST(v_pay_received, v_cash_remaining);
                v_pay_change := v_pay_received - v_pay_applied;
                v_cash_remaining := v_cash_remaining - v_pay_applied;
                v_change_total := v_change_total + v_pay_change;
            END IF;

            INSERT INTO public.sale_payments (
                company_id, sale_id, payment_method, amount,
                received_amount, change_amount
            ) VALUES (
                p_company_id, v_id, v_pay_method, v_pay_applied,
                v_pay_received, v_pay_change
            );
        END LOOP;
    ELSIF p_payments IS NULL AND v_total > 0 THEN
        INSERT INTO public.sale_payments (
            company_id, sale_id, payment_method, amount,
            received_amount, change_amount
        ) VALUES (
            p_company_id, v_id, p_payment_method, v_total, v_total, 0
        );
    END IF;

    UPDATE public.sales SET status = 'CONCLUIDA' WHERE id = v_id;
    RETURN jsonb_build_object(
        'id', v_id,
        'cliente', v_client_name,
        'total', v_total,
        'original_total', v_gross_total,
        'discount', v_discount_total,
        'sale_discount_type', v_sale_type,
        'sale_discount_value', v_sale_value,
        'payment_method', v_primary_method,
        'change_total', v_change_total,
        'created_on', (SELECT created_on FROM public.sales WHERE id = v_id),
        'seller_id', v_seller,
        'discount_applied_by', CASE
            WHEN v_discount_total > 0 THEN v_seller ELSE NULL END,
        'discount_authorized_by', v_authorizer,
        'discount_authorized_by_name', COALESCE(v_authorizer_name, ''),
        'payments', (
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'id', sp.id,
                'payment_method', sp.payment_method,
                'amount', sp.amount,
                'received_amount', sp.received_amount,
                'change_amount', sp.change_amount
            ) ORDER BY sp.created_on, sp.id), '[]'::jsonb)
              FROM public.sale_payments sp
             WHERE sp.sale_id = v_id
        ),
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

-- A interface antiga continua compatível, mas também passa pela regra de limite.
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
