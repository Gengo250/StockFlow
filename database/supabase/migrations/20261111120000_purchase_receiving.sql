BEGIN;

CREATE TYPE public.purchase_status AS ENUM ('RASCUNHO', 'RECEBIDA');

CREATE TABLE public.purchases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    supplier_id uuid NOT NULL,
    status public.purchase_status NOT NULL DEFAULT 'RASCUNHO',
    created_by uuid,
    created_on timestamptz NOT NULL DEFAULT now(),
    received_on timestamptz,
    UNIQUE (company_id, id),
    UNIQUE (company_id, id, supplier_id),
    FOREIGN KEY (company_id, supplier_id)
        REFERENCES public.suppliers (company_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_purchases_received_on CHECK (
        (status = 'RASCUNHO' AND received_on IS NULL)
        OR (status = 'RECEBIDA' AND received_on IS NOT NULL)
    )
);
CREATE INDEX idx_purchases_company_created
    ON public.purchases (company_id, created_on DESC);

CREATE TABLE public.purchase_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL,
    purchase_id uuid NOT NULL,
    product_id uuid NOT NULL REFERENCES public.products (id) ON DELETE RESTRICT,
    quantity integer NOT NULL CHECK (quantity > 0),
    created_on timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, purchase_id, id),
    FOREIGN KEY (company_id, purchase_id)
        REFERENCES public.purchases (company_id, id) ON DELETE CASCADE
);
CREATE INDEX idx_purchase_items_purchase
    ON public.purchase_items (company_id, purchase_id, id);

ALTER TABLE public.stock_movements ADD COLUMN purchase_id uuid;
ALTER TABLE public.stock_movements
    ADD CONSTRAINT fk_stock_movements_purchase_supplier
    FOREIGN KEY (company_id, purchase_id, supplier_id)
    REFERENCES public.purchases (company_id, id, supplier_id)
    ON DELETE RESTRICT;
CREATE INDEX idx_stock_movements_purchase
    ON public.stock_movements (company_id, purchase_id)
    WHERE purchase_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.fn_create_purchase(
    p_company_id uuid, p_supplier_id uuid, p_items jsonb
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_purchase_id uuid;
    v_product_id uuid;
    v_item record;
BEGIN
    IF NOT public.fn_has_role(
        p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]
    ) THEN
        RAISE EXCEPTION 'Sem permissão para criar compras nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array'
       OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'A compra deve ter pelo menos um item'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_items) AS entry(value)
         WHERE jsonb_typeof(entry.value) <> 'object'
            OR COALESCE(jsonb_typeof(entry.value->'product_code'), 'null') <> 'string'
            OR COALESCE(jsonb_typeof(entry.value->'quantity'), 'null') <> 'number'
            OR btrim(COALESCE(entry.value->>'product_code', '')) = ''
            OR COALESCE(entry.value->>'quantity', '') !~ '^[1-9][0-9]*$'
    ) THEN
        RAISE EXCEPTION 'Produto e quantidade inteira positiva são obrigatórios'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_items) AS entry(value)
         WHERE (entry.value->>'quantity')::numeric > 1000000
    ) THEN
        RAISE EXCEPTION 'A quantidade por item não pode exceder 1000000'
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM 1 FROM public.suppliers
     WHERE id = p_supplier_id AND company_id = p_company_id AND active
       FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Fornecedor não encontrado, inativo ou sem permissão'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO public.purchases (company_id, supplier_id, created_by)
    VALUES (p_company_id, p_supplier_id, public.fn_current_user_id())
    RETURNING id INTO v_purchase_id;

    FOR v_item IN
        SELECT entry.value->>'product_code' AS product_code,
               (entry.value->>'quantity')::integer AS quantity
          FROM jsonb_array_elements(p_items) AS entry(value)
         ORDER BY entry.value->>'product_code'
    LOOP
        SELECT id INTO v_product_id
          FROM public.products
         WHERE company_id = p_company_id
           AND barcode = v_item.product_code AND active
           FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Produto % não encontrado, inativo ou sem permissão',
                v_item.product_code USING ERRCODE = 'foreign_key_violation';
        END IF;
        INSERT INTO public.purchase_items (
            company_id, purchase_id, product_id, quantity
        ) VALUES (p_company_id, v_purchase_id, v_product_id, v_item.quantity);
    END LOOP;
    RETURN v_purchase_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_list_company_purchases(p_company_id uuid)
RETURNS TABLE (
    id uuid, supplier_id uuid, supplier_name text, status public.purchase_status,
    created_on timestamptz, received_on timestamptz, items jsonb
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF NOT public.fn_has_role(
        p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]
    ) THEN
        RAISE EXCEPTION 'Sem permissão para consultar compras nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN QUERY
    SELECT p.id, p.supplier_id, s.name, p.status, p.created_on, p.received_on,
           COALESCE((
               SELECT jsonb_agg(jsonb_build_object(
                   'id', i.id, 'product_id', i.product_id,
                   'product_code', pr.barcode, 'product_name', pr.name,
                   'quantity', i.quantity
               ) ORDER BY i.id)
                 FROM public.purchase_items i
                 JOIN public.products pr ON pr.id = i.product_id
                WHERE i.company_id = p.company_id AND i.purchase_id = p.id
           ), '[]'::jsonb)
      FROM public.purchases p
      JOIN public.suppliers s
        ON s.id = p.supplier_id AND s.company_id = p.company_id
     WHERE p.company_id = p_company_id
     ORDER BY p.created_on DESC, p.id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_receive_purchase(p_purchase_id uuid)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_purchase public.purchases%ROWTYPE;
    v_item record;
    v_actor uuid := public.fn_current_user_id();
BEGIN
    SELECT * INTO v_purchase
      FROM public.purchases WHERE id = p_purchase_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Compra não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT public.fn_has_role(
        v_purchase.company_id, ARRAY['ADMIN','STOCK']::public.user_role[]
    ) THEN
        RAISE EXCEPTION 'Compra não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF v_purchase.status <> 'RASCUNHO' THEN
        RAISE EXCEPTION 'Só compras em rascunho podem ser recebidas'
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM 1 FROM public.suppliers
     WHERE id = v_purchase.supplier_id
       AND company_id = v_purchase.company_id AND active
       FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'O fornecedor da compra não está ativo'
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.purchase_items
         WHERE company_id = v_purchase.company_id AND purchase_id = v_purchase.id
    ) THEN
        RAISE EXCEPTION 'A compra não possui itens'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM public.purchase_items i
          LEFT JOIN public.products p
            ON p.id = i.product_id AND p.company_id = i.company_id AND p.active
         WHERE i.company_id = v_purchase.company_id
           AND i.purchase_id = v_purchase.id AND p.id IS NULL
    ) THEN
        RAISE EXCEPTION 'A compra contém produto inativo ou de outra empresa'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    PERFORM p.id
      FROM public.products p
      JOIN public.purchase_items i
        ON i.product_id = p.id AND i.company_id = p.company_id
     WHERE i.company_id = v_purchase.company_id
       AND i.purchase_id = v_purchase.id
     ORDER BY p.id
       FOR UPDATE OF p;

    FOR v_item IN
        SELECT i.product_id, i.quantity
          FROM public.purchase_items i
         WHERE i.company_id = v_purchase.company_id
           AND i.purchase_id = v_purchase.id
         ORDER BY i.product_id, i.id
    LOOP
        INSERT INTO public.stock_movements (
            company_id, product_id, supplier_id, purchase_id,
            kind, quantity, status, note, created_by, confirmed_on
        ) VALUES (
            v_purchase.company_id, v_item.product_id, v_purchase.supplier_id,
            v_purchase.id, 'ENTRADA', v_item.quantity, 'CONFIRMADA',
            'Entrada de compra ' || v_purchase.id::text, v_actor, now()
        );
    END LOOP;
    UPDATE public.purchases
       SET status = 'RECEBIDA', received_on = now()
     WHERE id = v_purchase.id;
END;
$$;

ALTER TABLE public.purchases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.purchases, public.purchase_items
    FROM PUBLIC, anon, authenticated, app_backend;
GRANT SELECT ON public.purchases, public.purchase_items
    TO app_backend, authenticated;

DROP POLICY IF EXISTS purchases_select ON public.purchases;
CREATE POLICY purchases_select ON public.purchases
    FOR SELECT TO app_backend, authenticated
    USING (public.fn_has_role(company_id, ARRAY['ADMIN','STOCK']::public.user_role[]));
DROP POLICY IF EXISTS purchase_items_select ON public.purchase_items;
CREATE POLICY purchase_items_select ON public.purchase_items
    FOR SELECT TO app_backend, authenticated
    USING (public.fn_has_role(company_id, ARRAY['ADMIN','STOCK']::public.user_role[]));

REVOKE ALL ON FUNCTION public.fn_create_purchase(uuid, uuid, jsonb)
    FROM PUBLIC, anon, authenticated, app_backend;
REVOKE ALL ON FUNCTION public.fn_list_company_purchases(uuid)
    FROM PUBLIC, anon, authenticated, app_backend;
REVOKE ALL ON FUNCTION public.fn_receive_purchase(uuid)
    FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_create_purchase(uuid, uuid, jsonb)
    TO app_backend, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_list_company_purchases(uuid)
    TO app_backend, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_receive_purchase(uuid)
    TO app_backend, authenticated;

COMMIT;
