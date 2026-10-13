-- Gestão de fornecedores. Escritas protegidas por papel e escopo de empresa.

CREATE OR REPLACE FUNCTION public.fn_list_company_suppliers(
    p_company_id uuid,
    p_search text DEFAULT NULL
) RETURNS TABLE (
    id uuid,
    name text,
    document text,
    phone text,
    email text,
    address text,
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
    IF NOT public.fn_has_role(
        p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]
    ) THEN
        RAISE EXCEPTION 'Sem permissão para consultar fornecedores nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN QUERY
    SELECT s.id, s.name, s.document, s.phone, s.email, s.address,
           s.active, s.created_on, s.updated_on
      FROM public.suppliers s
     WHERE s.company_id = p_company_id
       AND (
           v_search = ''
           OR s.name ILIKE '%' || v_search || '%'
           OR lower(s.email) LIKE '%' || v_search || '%'
           OR lower(s.address) LIKE '%' || v_search || '%'
           OR (v_digits <> '' AND
               regexp_replace(s.phone, '\D', '', 'g') LIKE '%' || v_digits || '%')
           OR (v_digits <> '' AND COALESCE(s.document, '') LIKE '%' || v_digits || '%')
       )
     ORDER BY lower(s.name), s.id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_supplier(
    p_company_id uuid,
    p_name text,
    p_document text DEFAULT NULL,
    p_phone text DEFAULT '',
    p_email text DEFAULT '',
    p_address text DEFAULT ''
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
    v_document text := NULLIF(regexp_replace(COALESCE(p_document, ''), '\D', '', 'g'), '');
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para cadastrar fornecedores nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_name IS NULL OR btrim(p_name) = '' THEN
        RAISE EXCEPTION 'Nome ou razão social do fornecedor é obrigatório'
            USING ERRCODE = 'not_null_violation';
    END IF;
    IF NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL
       AND p_document !~ '^[0-9./[:space:]-]+$' THEN
        RAISE EXCEPTION 'CPF/CNPJ do fornecedor é inválido'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL
       AND (v_document IS NULL OR NOT public.fn_valid_br_document(v_document)) THEN
        RAISE EXCEPTION 'CPF/CNPJ do fornecedor é inválido'
            USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.suppliers (company_id, name, document, phone, email, address)
    VALUES (p_company_id, btrim(p_name), v_document,
            btrim(COALESCE(p_phone, '')), btrim(COALESCE(p_email, '')),
            btrim(COALESCE(p_address, '')))
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_update_supplier(
    p_supplier_id uuid,
    p_name text,
    p_document text DEFAULT NULL,
    p_phone text DEFAULT '',
    p_email text DEFAULT '',
    p_address text DEFAULT '',
    p_active boolean DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company_id uuid;
    v_document text := NULLIF(regexp_replace(COALESCE(p_document, ''), '\D', '', 'g'), '');
BEGIN
    SELECT company_id INTO v_company_id FROM public.suppliers WHERE id = p_supplier_id;
    IF v_company_id IS NULL
       OR NOT public.fn_has_role(v_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Fornecedor não encontrado ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_name IS NULL OR btrim(p_name) = '' THEN
        RAISE EXCEPTION 'Nome ou razão social do fornecedor é obrigatório'
            USING ERRCODE = 'not_null_violation';
    END IF;
    IF NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL
       AND p_document !~ '^[0-9./[:space:]-]+$' THEN
        RAISE EXCEPTION 'CPF/CNPJ do fornecedor é inválido'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL
       AND (v_document IS NULL OR NOT public.fn_valid_br_document(v_document)) THEN
        RAISE EXCEPTION 'CPF/CNPJ do fornecedor é inválido'
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.suppliers
       SET name = btrim(p_name),
           document = v_document,
           phone = btrim(COALESCE(p_phone, '')),
           email = btrim(COALESCE(p_email, '')),
           address = btrim(COALESCE(p_address, '')),
           active = COALESCE(p_active, active),
           updated_on = now()
     WHERE id = p_supplier_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_set_supplier_active(
    p_supplier_id uuid,
    p_active boolean
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company_id uuid;
BEGIN
    SELECT company_id INTO v_company_id FROM public.suppliers WHERE id = p_supplier_id;
    IF v_company_id IS NULL
       OR NOT public.fn_has_role(v_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Fornecedor não encontrado ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_active IS NULL THEN
        RAISE EXCEPTION 'p_active é obrigatório' USING ERRCODE = 'not_null_violation';
    END IF;
    UPDATE public.suppliers SET active = p_active, updated_on = now()
     WHERE id = p_supplier_id;
END;
$$;

-- Set-or-clear the optional supplier of a product without allowing a
-- cross-company or inactive supplier reference.
CREATE OR REPLACE FUNCTION public.fn_set_product_supplier(
    p_product_id uuid,
    p_supplier_id uuid DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company_id uuid;
    v_current_supplier uuid;
BEGIN
    SELECT company_id, supplier_id INTO v_company_id, v_current_supplier
      FROM public.products WHERE id = p_product_id FOR UPDATE;
    IF v_company_id IS NULL
       OR NOT public.fn_has_role(v_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Produto não encontrado ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_supplier_id IS NOT NULL AND p_supplier_id IS DISTINCT FROM v_current_supplier
       AND NOT EXISTS (
        SELECT 1 FROM public.suppliers
         WHERE id = p_supplier_id AND company_id = v_company_id AND active
    ) THEN
        RAISE EXCEPTION 'Fornecedor não encontrado, inativo ou sem permissão'
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    UPDATE public.products SET supplier_id = p_supplier_id WHERE id = p_product_id;
END;
$$;

-- Compra/entrada e vínculo são uma única chamada RPC: qualquer recusa do
-- fornecedor desfaz também o registro da movimentação.
CREATE OR REPLACE FUNCTION public.fn_register_supplier_movement(
    p_company_id uuid,
    p_product_id uuid,
    p_kind public.movement_kind,
    p_quantity integer,
    p_supplier_id uuid,
    p_note text DEFAULT NULL,
    p_confirm boolean DEFAULT false
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
BEGIN
    IF p_kind <> 'ENTRADA' THEN
        RAISE EXCEPTION 'Fornecedor só pode ser associado a uma entrada'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para registrar compras nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_supplier_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM public.suppliers
         WHERE id = p_supplier_id AND company_id = p_company_id AND active
    ) THEN
        RAISE EXCEPTION 'Fornecedor obrigatório, ativo e da empresa é necessário'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    v_id := public.fn_register_movement(
        p_company_id, p_product_id, p_kind, p_quantity, p_note, p_confirm
    );
    UPDATE public.stock_movements SET supplier_id = p_supplier_id WHERE id = v_id;
    RETURN v_id;
END;
$$;
