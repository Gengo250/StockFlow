-- US22: descontos por item/venda, limites por perfil e auditoria de aprovação.
-- Correção autorizada antes da aplicação: uma gerada não pode referenciar outra.

ALTER TABLE public.sales
    ADD COLUMN original_total numeric(10,2)
        GENERATED ALWAYS AS (total + discount) STORED,
    ADD COLUMN sale_discount_type text NOT NULL DEFAULT 'FIXED'
        CHECK (sale_discount_type IN ('FIXED', 'PERCENTAGE')),
    ADD COLUMN sale_discount_value numeric(10,2) NOT NULL DEFAULT 0
        CHECK (sale_discount_value >= 0 AND
               (sale_discount_type <> 'PERCENTAGE' OR sale_discount_value <= 100)),
    ADD COLUMN discount_applied_by uuid,
    ADD COLUMN discount_authorized_by uuid;

ALTER TABLE public.sale_items
    ADD COLUMN discount_type text NOT NULL DEFAULT 'FIXED'
        CHECK (discount_type IN ('FIXED', 'PERCENTAGE')),
    ADD COLUMN discount_value numeric(10,2) NOT NULL DEFAULT 0
        CHECK (discount_value >= 0 AND
               (discount_type <> 'PERCENTAGE' OR discount_value <= 100)),
    ADD COLUMN discount_amount numeric(10,2) NOT NULL DEFAULT 0
        CHECK (discount_amount >= 0 AND
               discount_amount <= quantity * unit_price),
    ADD COLUMN final_subtotal numeric(10,2)
        GENERATED ALWAYS AS (quantity * unit_price - discount_amount) STORED;

CREATE TABLE public.sale_discount_limits (
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    role public.user_role NOT NULL,
    limit_percent numeric(5,2)
        CHECK (limit_percent IS NULL OR limit_percent BETWEEN 0 AND 100),
    updated_by uuid,
    updated_on timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, role),
    CHECK (role = 'SELLER')
);
ALTER TABLE public.sale_discount_limits ENABLE ROW LEVEL SECURITY;

DROP FUNCTION IF EXISTS public.fn_list_sales(
    uuid, text, timestamptz, timestamptz, uuid, uuid,
    public.sale_status, text, integer, integer
);
CREATE OR REPLACE FUNCTION public.fn_list_sales(
    p_company_id uuid,
    p_sale_id    text               DEFAULT NULL,
    p_from       timestamptz        DEFAULT NULL,
    p_to         timestamptz        DEFAULT NULL,
    p_client_id  uuid               DEFAULT NULL,
    p_seller_id  uuid               DEFAULT NULL,
    p_status     public.sale_status DEFAULT NULL,
    p_sort       text               DEFAULT 'DATA_DESC',
    p_limit      integer            DEFAULT 50,
    p_offset     integer            DEFAULT 0
)
RETURNS TABLE (
    id               uuid,
    client_id        uuid,
    client_name      text,
    seller_id        uuid,
    seller_name      text,
    payment_method   public.payment_method,
    discount         numeric,
    original_total   numeric,
    discount_applied_by uuid,
    discount_applied_by_name text,
    discount_authorized_by uuid,
    discount_authorized_by_name text,
    total            numeric,
    status           public.sale_status,
    created_on       timestamptz,
    items            jsonb,
    reversal_kind    public.sale_reversal_kind,
    reversal_reason  text,
    reversal_on      timestamptz,
    reversal_by_name text,
    total_count      bigint
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
-- ATENÇÃO: os nomes de RETURNS TABLE viram variáveis e competem com os
-- nomes de coluna. TODA referência abaixo precisa continuar qualificada
-- (`f.id`, `f.total`, ...). Já existiu aqui um `#variable_conflict
-- use_column` como rede, e ele saiu: era a única diretiva desse tipo em
-- todo o `database/`, e a migration que a carregava chegou ao remoto sem
-- criar função nenhuma. Qualificar é suficiente e não depende de como o
-- arquivo é parseado no caminho até o banco.
BEGIN
    -- SECURITY DEFINER passa por cima da RLS, então a checagem que
    -- `sales_select` faz na tabela precisa ser repetida aqui. Sem ela, esta
    -- função vira a porta dos fundos do próprio histórico.
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Sem permissão para consultar o histórico desta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- Página sem teto é `list_all` com outro nome, e devolveria ao cliente
    -- exatamente o volume que a paginação existe para evitar.
    IF p_limit IS NULL OR p_limit <= 0 OR p_limit > 200 THEN
        RAISE EXCEPTION 'Tamanho de página inválido: %', p_limit
            USING ERRCODE = 'check_violation';
    END IF;
    IF p_offset IS NULL OR p_offset < 0 THEN
        RAISE EXCEPTION 'Deslocamento de página inválido: %', p_offset
            USING ERRCODE = 'check_violation';
    END IF;
    IF p_sort IS NULL OR p_sort NOT IN
       ('DATA_DESC', 'DATA_ASC', 'VALOR_DESC', 'VALOR_ASC', 'CLIENTE_ASC') THEN
        RAISE EXCEPTION 'Ordenação desconhecida: %', p_sort
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN QUERY
    WITH filtradas AS (
        SELECT s.*
          FROM public.sales s
         WHERE s.company_id = p_company_id
           -- Casa por PREFIXO: é como a tela mostra o identificador, e
           -- digitar o uuid inteiro para achar uma venda não é consulta.
           AND (p_sale_id   IS NULL OR s.id::text LIKE lower(btrim(p_sale_id)) || '%')
           AND (p_from      IS NULL OR s.created_on >= p_from)
           -- Limite superior EXCLUSIVO: o chamador manda o início do dia
           -- seguinte, e assim o último dia do período entra inteiro.
           AND (p_to        IS NULL OR s.created_on < p_to)
           AND (p_client_id IS NULL OR s.client_id = p_client_id)
           AND (p_seller_id IS NULL OR s.created_by = p_seller_id)
           -- Sem um status explícito, o histórico contém apenas vendas
           -- finalizadas. PENDENTE continua consultável quando selecionada.
           AND (p_status IS NOT NULL OR s.status <> 'PENDENTE')
           AND (p_status     IS NULL OR s.status = p_status)
    )
    SELECT f.id,
           f.client_id,
           f.client_name,
           f.created_by,
           COALESCE(ua.name, ''),
           f.payment_method,
           f.discount,
           f.original_total,
           f.discount_applied_by,
           COALESCE(da.name, ''),
           f.discount_authorized_by,
           COALESCE(au.name, ''),
           f.total,
           f.status,
           f.created_on,
           COALESCE((SELECT jsonb_agg(to_jsonb(i) ORDER BY i.created_on, i.id)
                       FROM public.sale_items i
                      WHERE i.sale_id = f.id), '[]'::jsonb),
           r.kind,
           r.reason,
           r.created_on,
           COALESCE(rua.name, ''),
           -- Calculado ANTES do LIMIT: é o total que casa com o filtro, que
           -- é o que a tela precisa para saber quantas páginas existem. Uma
           -- segunda consulta de contagem poderia divergir desta sob
           -- concorrência, e a tela prometeria página que não existe.
           count(*) OVER ()
      FROM filtradas f
      -- LEFT JOIN nos três: a venda pode não ter reversão, e conta removida
      -- não pode apagar a linha do histórico.
      LEFT JOIN public.sale_reversals r   ON r.sale_id = f.id
      LEFT JOIN public.user_accounts  ua  ON ua.id = f.created_by
      LEFT JOIN public.user_accounts  da  ON da.id = f.discount_applied_by
      LEFT JOIN public.user_accounts  au  ON au.id = f.discount_authorized_by
      LEFT JOIN public.user_accounts  rua ON rua.id = r.created_by
     ORDER BY
        CASE WHEN p_sort = 'DATA_DESC'   THEN f.created_on END DESC,
        CASE WHEN p_sort = 'DATA_ASC'    THEN f.created_on END ASC,
        CASE WHEN p_sort = 'VALOR_DESC'  THEN f.total      END DESC,
        CASE WHEN p_sort = 'VALOR_ASC'   THEN f.total      END ASC,
        CASE WHEN p_sort = 'CLIENTE_ASC' THEN lower(f.client_name) END ASC,
        -- Desempate obrigatório: duas vendas no mesmo instante têm ordem
        -- indefinida sem ele, e a página 2 repetiria ou pularia linha.
        f.id DESC
     LIMIT p_limit OFFSET p_offset;
END;
$$;

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
-- Toda conclusão de venda, inclusive caminhos legados, aplica o limite de desconto.
CREATE OR REPLACE FUNCTION public.fn_validate_sale_discount_limit()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_seller_role public.user_role;
    v_limit numeric;
    v_original_total numeric;
    v_percent numeric := 0;
    v_item_discount_total numeric;
    v_additional_discount numeric;
BEGIN
    v_original_total := NEW.total + NEW.discount;
    SELECT COALESCE(sum(si.discount_amount), 0) INTO v_item_discount_total
      FROM public.sale_items si
     WHERE si.sale_id = NEW.id AND si.company_id = NEW.company_id;
    v_additional_discount := NEW.discount - v_item_discount_total;
    IF v_additional_discount < 0 THEN
        RAISE EXCEPTION 'Desconto total menor que os descontos dos itens da venda'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.discount > 0 THEN
        NEW.discount_applied_by := COALESCE(
            NEW.discount_applied_by, NEW.created_by
        );
        -- Completar somente metadado FIXED legado. Desconto exclusivo dos
        -- itens e PERCENTAGE zero explícito devem continuar com parcela zero.
        IF NEW.sale_discount_type = 'FIXED' AND NEW.sale_discount_value = 0
           AND v_additional_discount > 0 THEN
            NEW.sale_discount_value := v_additional_discount;
        END IF;
    END IF;

    IF NEW.discount > 0 AND NEW.discount_applied_by IS NULL THEN
        RAISE EXCEPTION 'A autoria do desconto é obrigatória'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT cu.role INTO v_seller_role
      FROM public.company_users cu
     WHERE cu.company_id = NEW.company_id
       AND cu.user_account_id = NEW.created_by
       AND cu.active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Responsável pela venda não pertence à empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF v_seller_role = 'SELLER' THEN
        SELECT COALESCE((
            SELECT sdl.limit_percent
              FROM public.sale_discount_limits sdl
             WHERE sdl.company_id = NEW.company_id AND sdl.role = 'SELLER'
        ), 10.00) INTO v_limit;

        IF v_original_total > 0 THEN
            v_percent := NEW.discount * 100 / v_original_total;
        END IF;
        IF v_percent > v_limit
           AND (
               NEW.discount_authorized_by IS NULL
               OR NOT public.fn_is_admin(
                   NEW.discount_authorized_by, NEW.company_id
               )
           ) THEN
            RAISE EXCEPTION
                'Desconto acima do limite de %%%: aprovação de ADMIN necessária',
                v_limit
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sale_discount_guard ON public.sales;
CREATE TRIGGER trg_sale_discount_guard
    BEFORE UPDATE OF status ON public.sales
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'CONCLUIDA')
    EXECUTE FUNCTION public.fn_validate_sale_discount_limit();

REVOKE ALL ON FUNCTION public.fn_list_sales(
    uuid, text, timestamptz, timestamptz, uuid, uuid,
    public.sale_status, text, integer, integer
) FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_list_sales(
    uuid, text, timestamptz, timestamptz, uuid, uuid,
    public.sale_status, text, integer, integer
) TO app_backend, authenticated;
REVOKE ALL ON FUNCTION public.fn_get_sale_discount_limits(uuid)
    FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_get_sale_discount_limits(uuid)
    TO app_backend, authenticated;
REVOKE ALL ON FUNCTION public.fn_set_sale_discount_limit(
    uuid, public.user_role, numeric
) FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_set_sale_discount_limit(
    uuid, public.user_role, numeric
) TO app_backend, authenticated;
REVOKE ALL ON FUNCTION public.fn_register_sale_with_discounts(
    uuid, uuid, jsonb, public.payment_method, text, numeric, uuid
) FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_register_sale_with_discounts(
    uuid, uuid, jsonb, public.payment_method, text, numeric, uuid
) TO app_backend, authenticated;
REVOKE ALL ON FUNCTION public.fn_register_sale(
    uuid, uuid, jsonb, public.payment_method, numeric
) FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_register_sale(
    uuid, uuid, jsonb, public.payment_method, numeric
) TO app_backend, authenticated;
