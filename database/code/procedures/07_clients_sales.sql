-- Persistência de clientes e do fluxo de vendas atual.

CREATE OR REPLACE FUNCTION public.fn_list_company_clients(
    p_company_id uuid,
    p_search text DEFAULT NULL
) RETURNS TABLE (
    client_id uuid,
    name text,
    document text,
    email text,
    phone text,
    notes text,
    active boolean,
    created_on timestamptz,
    updated_on timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_search text := lower(btrim(COALESCE(p_search, '')));
    v_digits text := regexp_replace(COALESCE(p_search, ''), '\D', '', 'g');
BEGIN
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Sem permissão para consultar clientes nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN QUERY
    SELECT c.id, c.name, c.document, c.email, c.phone, c.notes,
           c.active, c.created_on, c.updated_on
      FROM public.clients c
     WHERE c.company_id = p_company_id
       AND (
           v_search = ''
           OR c.name ILIKE '%' || v_search || '%'
           OR lower(c.email) LIKE '%' || v_search || '%'
           OR (v_digits <> '' AND
               regexp_replace(c.phone, '\D', '', 'g') LIKE '%' || v_digits || '%')
           OR (v_digits <> '' AND
               COALESCE(c.document, '') LIKE '%' || v_digits || '%')
       )
     ORDER BY lower(c.name), c.id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_client(
    p_company_id uuid,
    p_name text,
    p_document text DEFAULT NULL,
    p_email text DEFAULT '',
    p_phone text DEFAULT '',
    p_notes text DEFAULT ''
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
    v_document text := NULLIF(regexp_replace(COALESCE(p_document, ''), '\D', '', 'g'), '');
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para cadastrar clientes nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_name IS NULL OR btrim(p_name) = '' THEN
        RAISE EXCEPTION 'Nome do cliente é obrigatório'
            USING ERRCODE = 'not_null_violation';
    END IF;
    IF NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL
       AND p_document !~ '^[0-9./[:space:]-]+$' THEN
        RAISE EXCEPTION 'CPF/CNPJ do cliente é inválido'
            USING ERRCODE = 'check_violation';
    END IF;
    IF (NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL AND v_document IS NULL)
       OR (v_document IS NOT NULL AND NOT public.fn_valid_br_document(v_document)) THEN
        RAISE EXCEPTION 'CPF/CNPJ do cliente é inválido'
            USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.clients (company_id, name, document, email, phone, notes)
    VALUES (p_company_id, btrim(p_name), v_document,
            btrim(COALESCE(p_email, '')), btrim(COALESCE(p_phone, '')),
            btrim(COALESCE(p_notes, '')))
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_update_client(
    p_client_id uuid,
    p_name text,
    p_document text DEFAULT NULL,
    p_email text DEFAULT '',
    p_phone text DEFAULT '',
    p_notes text DEFAULT '',
    p_active boolean DEFAULT true
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company_id uuid;
    v_document text := NULLIF(regexp_replace(COALESCE(p_document, ''), '\D', '', 'g'), '');
BEGIN
    SELECT company_id INTO v_company_id
      FROM public.clients WHERE id = p_client_id;
    IF v_company_id IS NULL
       OR NOT public.fn_has_role(v_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Cliente não encontrado ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_name IS NULL OR btrim(p_name) = '' THEN
        RAISE EXCEPTION 'Nome do cliente é obrigatório'
            USING ERRCODE = 'not_null_violation';
    END IF;
    IF NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL
       AND p_document !~ '^[0-9./[:space:]-]+$' THEN
        RAISE EXCEPTION 'CPF/CNPJ do cliente é inválido'
            USING ERRCODE = 'check_violation';
    END IF;
    IF (NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL AND v_document IS NULL)
       OR (v_document IS NOT NULL AND NOT public.fn_valid_br_document(v_document)) THEN
        RAISE EXCEPTION 'CPF/CNPJ do cliente é inválido'
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.clients
       SET name = btrim(p_name),
           document = v_document,
           email = btrim(COALESCE(p_email, '')),
           phone = btrim(COALESCE(p_phone, '')),
           notes = btrim(COALESCE(p_notes, '')),
           active = COALESCE(p_active, active)
     WHERE id = p_client_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_set_client_active(
    p_client_id uuid,
    p_active boolean
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company_id uuid;
BEGIN
    SELECT company_id INTO v_company_id
      FROM public.clients WHERE id = p_client_id;
    IF v_company_id IS NULL
       OR NOT public.fn_has_role(v_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Cliente não encontrado ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    UPDATE public.clients SET active = p_active WHERE id = p_client_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_register_sale(
    p_company_id uuid,
    p_client_id uuid,
    p_product_id uuid,
    p_total numeric
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
    v_client_name text;
    v_product_name text;
    v_product_code text;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para registrar vendas nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_total IS NULL OR p_total < 0 THEN
        RAISE EXCEPTION 'Valor da venda inválido' USING ERRCODE = 'check_violation';
    END IF;

    SELECT name INTO v_client_name
      FROM public.clients
     WHERE id = p_client_id AND company_id = p_company_id AND active
     FOR SHARE;
    IF v_client_name IS NULL THEN
        RAISE EXCEPTION 'Cliente não encontrado, inativo ou sem permissão'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT name, barcode INTO v_product_name, v_product_code
      FROM public.products
     WHERE id = p_product_id AND company_id = p_company_id AND active
     FOR SHARE;
    IF v_product_name IS NULL THEN
        RAISE EXCEPTION 'Produto não encontrado, inativo ou sem permissão'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO public.sales (
        company_id, client_id, product_id, client_name,
        product_name, product_code, total, created_by
    ) VALUES (
        p_company_id, p_client_id, p_product_id, v_client_name,
        v_product_name, COALESCE(v_product_code, ''), p_total,
        public.fn_current_user_id()
    )
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
