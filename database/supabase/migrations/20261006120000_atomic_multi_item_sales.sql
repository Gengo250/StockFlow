-- US012: sale items and their confirmed stock exits are committed together.

ALTER TABLE public.sales
    ADD CONSTRAINT uq_sales_company_id UNIQUE (company_id, id);

CREATE TABLE public.sale_items (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL,
    sale_id      uuid NOT NULL,
    product_id   uuid,
    product_code text NOT NULL,
    product_name text NOT NULL,
    line_number  integer NOT NULL CHECK (line_number > 0),
    quantity     integer NOT NULL CHECK (quantity > 0),
    unit_price   numeric(10,2) NOT NULL CHECK (unit_price >= 0),
    subtotal     numeric(10,2) NOT NULL CHECK (subtotal >= 0),
    created_on   timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE CASCADE,
    FOREIGN KEY (product_id)
        REFERENCES public.products (id) ON DELETE SET NULL,
    UNIQUE (sale_id, line_number)
);
CREATE INDEX idx_sale_items_sale_created
    ON public.sale_items (sale_id, line_number);

ALTER TABLE public.sale_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sale_items FROM PUBLIC, anon, authenticated, app_backend;
GRANT SELECT ON public.sale_items TO app_backend, authenticated;
CREATE POLICY sale_items_select ON public.sale_items
    FOR SELECT TO app_backend, authenticated
    USING (public.fn_is_member(company_id));

DROP FUNCTION IF EXISTS public.fn_register_sale(uuid, uuid, uuid, numeric);

CREATE OR REPLACE FUNCTION public.fn_register_sale(
    p_company_id uuid,
    p_client_id uuid,
    p_items jsonb
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
    v_client_name text;
    v_item record;
    v_product record;
    v_product_ids uuid[] := ARRAY[]::uuid[];
    v_product_codes text[] := ARRAY[]::text[];
    v_product_names text[] := ARRAY[]::text[];
    v_unit_prices numeric[] := ARRAY[]::numeric[];
    v_total numeric := 0;
    v_index integer;
    v_line_number integer := 0;
    v_created_on timestamptz;
    v_line record;
    v_line_quantity integer;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para registrar vendas nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' THEN
        RAISE EXCEPTION 'Os itens da venda devem ser uma lista'
            USING ERRCODE = 'check_violation';
    END IF;
    IF jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'A venda deve ter pelo menos um item'
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

    -- Aggregate duplicate SKU lines, then lock rows in a stable order.
    -- Concurrent sales wait for the product lock and validate the new balance.
    FOR v_item IN
        SELECT entry.value->>'product_code' AS product_code,
               sum((entry.value->>'quantity')::numeric)::integer AS quantity
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
        IF v_product.stock < v_item.quantity THEN
            RAISE EXCEPTION
                'Estoque insuficiente para o produto %: solicitado %, disponível %',
                v_item.product_code, v_item.quantity, v_product.stock
                USING ERRCODE = 'check_violation';
        END IF;

        v_product_ids := array_append(v_product_ids, v_product.id);
        v_product_codes := array_append(v_product_codes, v_product.barcode);
        v_product_names := array_append(v_product_names, v_product.name);
        v_unit_prices := array_append(v_unit_prices, v_product.sell_price);
        v_total := v_total + v_product.sell_price * v_item.quantity;
    END LOOP;

    IF cardinality(v_product_ids) = 0 OR v_total >= 100000000 THEN
        RAISE EXCEPTION 'Total ou itens da venda inválidos'
            USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.sales (
        company_id, client_id, product_id, client_name,
        product_name, product_code, total, created_by
    ) VALUES (
        p_company_id, p_client_id, v_product_ids[1], v_client_name,
        array_to_string(v_product_names, ', '),
        array_to_string(v_product_codes, ', '), v_total,
        public.fn_current_user_id()
    )
    RETURNING id, created_on INTO v_id, v_created_on;

    FOR v_line IN
        SELECT entry.value->>'product_code' AS product_code,
               (entry.value->>'quantity')::integer AS quantity
          FROM jsonb_array_elements(p_items) AS entry(value)
    LOOP
        v_line_number := v_line_number + 1;
        v_index := array_position(v_product_codes, v_line.product_code);
        v_line_quantity := v_line.quantity;
        INSERT INTO public.sale_items (
            company_id, sale_id, product_id, product_code, product_name,
            line_number, quantity, unit_price, subtotal
        ) VALUES (
            p_company_id, v_id, v_product_ids[v_index], v_line.product_code,
            v_product_names[v_index], v_line_number, v_line_quantity, v_unit_prices[v_index],
            v_unit_prices[v_index] * v_line_quantity
        );

        INSERT INTO public.stock_movements (
            company_id, product_id, kind, quantity, status, note,
            created_by, confirmed_on
        ) VALUES (
            p_company_id, v_product_ids[v_index], 'SAIDA', v_line_quantity,
            'CONFIRMADA', format('SAIDA_VENDA - venda %s', v_id),
            public.fn_current_user_id(), now()
        );
    END LOOP;
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
            ) ORDER BY si.line_number), '[]'::jsonb)
              FROM public.sale_items si
             WHERE si.sale_id = v_id
        )
    );
END;
$$;

REVOKE ALL ON FUNCTION public.fn_register_sale(uuid, uuid, jsonb)
    FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_register_sale(uuid, uuid, jsonb)
    TO app_backend, authenticated;
