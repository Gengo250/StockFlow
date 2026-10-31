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

    INSERT INTO public.clients (company_id, name, document, email, phone, notes,
                                created_by)
    VALUES (p_company_id, btrim(p_name), v_document,
            btrim(COALESCE(p_email, '')), btrim(COALESCE(p_phone, '')),
            btrim(COALESCE(p_notes, '')), public.fn_current_user_id())
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

-- Venda atômica do carrinho usado pela aplicação desktop. Os preços vêm do
-- catálogo; a tela envia apenas código e quantidade. Produtos são bloqueados
-- por código em ordem estável antes da conferência, e a conclusão usa o
-- gatilho existente para criar uma única saída por item.
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
    v_product_ids uuid[] := ARRAY[]::uuid[];
    v_product_codes text[] := ARRAY[]::text[];
    v_product_names text[] := ARRAY[]::text[];
    v_unit_prices numeric[] := ARRAY[]::numeric[];
    v_gross_total numeric := 0;
    v_total numeric;
    v_index integer;
    v_created_on timestamptz;
    v_line record;
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
    -- `round(p_discount, 2)` é o mesmo teto de precisão que
    -- `fn_create_complete_sale` já exigia, e ele não é cosmético: `discount` e
    -- `total` são numeric(10,2), mas arredondam por caminhos diferentes. Com
    -- 10.005 o banco gravava discount=10.01 e total=90.00 sobre subtotal
    -- 100.00 -- a linha deixava de fechar por R$ 0,01, justamente a
    -- reconciliação que a coluna `discount` existe para permitir auditar.
    IF p_payment_method IS NULL
       OR p_discount IS NULL OR p_discount < 0
       OR p_discount::text IN ('NaN', 'Infinity', '-Infinity')
       OR p_discount >= 100000000 OR p_discount <> round(p_discount, 2) THEN
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
    -- Bloco separado de propósito: só aqui a quantidade já passou pelo regex
    -- de dígitos acima, e o PostgreSQL não garante ordem de avaliação dentro
    -- de um mesmo OR -- juntar o cast ao teste de formato arriscaria estourar
    -- na conversão antes da recusa. O teto é o mesmo de
    -- `fn_create_complete_sale` e de `parse_quantity`; esta função aceitava
    -- até o limite de `integer`, e os três caminhos recusavam valores
    -- diferentes.
    IF EXISTS (
        SELECT 1
          FROM jsonb_array_elements(p_items) AS entry(value)
         WHERE (entry.value->>'quantity')::numeric > 1000000
    ) THEN
        RAISE EXCEPTION 'Quantidade deve ser inteira entre 1 e 1000000'
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
        v_index := array_position(v_product_codes, v_line.product_code);
        INSERT INTO public.sale_items (
            company_id, sale_id, product_id, product_name, product_code,
            quantity, unit_price
        ) VALUES (
            p_company_id, v_id, v_product_ids[v_index],
            v_product_names[v_index], v_product_codes[v_index],
            v_line.quantity, v_unit_prices[v_index]
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

-- ------------------------------------------------------------------ vendas
--
-- Duas portas de entrada, um só formato gravado (cabeçalho + itens):
--
--   fn_register_sale        venda de um produto com valor digitado pelo
--                           operador. Assinatura preservada da US07 porque é
--                           o que a tela de Vendas chama hoje.
--   fn_create_complete_sale venda com vários itens, forma de pagamento e
--                           desconto (US10). O preço unitário vem SEMPRE de
--                           products.sell_price: recebê-lo por parâmetro
--                           deixaria o chamador vender pelo valor que
--                           quisesse.
--
-- Ambas fecham a venda em CONCLUIDA, e é essa transição que dá baixa no
-- estoque (triggers/06_sale_completion.sql).

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
    IF p_total IS NULL OR p_total < 0 OR p_total::text IN ('NaN', 'Infinity', '-Infinity') THEN
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
     FOR UPDATE;
    IF v_product_name IS NULL THEN
        RAISE EXCEPTION 'Produto não encontrado, inativo ou sem permissão'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO public.sales (
        company_id, client_id, client_name, total, created_by
    ) VALUES (
        p_company_id, p_client_id, v_client_name, p_total,
        public.fn_current_user_id()
    )
    RETURNING id INTO v_id;

    INSERT INTO public.sale_items (
        company_id, sale_id, product_id, product_name, product_code,
        quantity, unit_price
    ) VALUES (
        p_company_id, v_id, p_product_id, v_product_name,
        COALESCE(v_product_code, ''), 1, p_total
    );

    UPDATE public.sales SET status = 'CONCLUIDA' WHERE id = v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_complete_sale(
    p_company_id     uuid,
    p_client_id      uuid,
    p_items          jsonb,
    p_payment_method public.payment_method DEFAULT 'DINHEIRO',
    p_discount       numeric DEFAULT 0
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id          uuid;
    v_client_name text;
    v_item        jsonb;
    v_product_id  uuid;
    v_quantity    integer;
    v_name        text;
    v_code        text;
    v_price       numeric(10,2);
    v_bruto       numeric := 0;
    v_total       numeric(10,2);
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para registrar vendas nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array'
       OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'Venda sem itens' USING ERRCODE = 'check_violation';
    END IF;

    IF p_discount IS NULL OR p_discount < 0
       OR p_discount >= 100000000 OR p_discount <> round(p_discount, 2)
       OR p_discount::text IN ('NaN', 'Infinity', '-Infinity') THEN
        RAISE EXCEPTION 'Desconto inválido' USING ERRCODE = 'check_violation';
    END IF;

    SELECT name INTO v_client_name
      FROM public.clients
     WHERE id = p_client_id AND company_id = p_company_id AND active
     FOR SHARE;
    IF v_client_name IS NULL THEN
        RAISE EXCEPTION 'Cliente não encontrado, inativo ou sem permissão'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF p_payment_method IS NULL THEN
        RAISE EXCEPTION 'Selecione uma forma de pagamento válida'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Trava TODOS os produtos em ordem estável antes de gravar. FOR SHARE
    -- deixava duas vendas travarem na conversão para UPDATE do saldo.
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
        IF jsonb_typeof(v_item) <> 'object'
           OR COALESCE(v_item->>'quantity', '') !~ '^[0-9]+$'
           OR (v_item->>'quantity')::numeric NOT BETWEEN 1 AND 1000000 THEN
            RAISE EXCEPTION 'Quantidade deve ser inteira entre 1 e 1000000'
                USING ERRCODE = 'check_violation';
        END IF;
    END LOOP;
    PERFORM p.id FROM public.products p
     WHERE p.company_id = p_company_id
       AND p.id IN (SELECT (i->>'product_id')::uuid FROM jsonb_array_elements(p_items) i)
     ORDER BY p.id FOR UPDATE;

    INSERT INTO public.sales (
        company_id, client_id, client_name, payment_method, discount,
        total, created_by
    ) VALUES (
        p_company_id, p_client_id, v_client_name, p_payment_method, p_discount,
        0, public.fn_current_user_id()
    )
    RETURNING id INTO v_id;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
        v_product_id := NULLIF(v_item->>'product_id', '')::uuid;
        v_quantity   := COALESCE((v_item->>'quantity')::integer, 0);

        IF v_quantity <= 0 THEN
            RAISE EXCEPTION 'Quantidade deve ser maior que zero (recebida: %)', v_quantity
                USING ERRCODE = 'check_violation';
        END IF;

        -- Preço, nome e código vêm do catálogo DESTA empresa. Produto de
        -- outra empresa não é encontrado aqui, e é esse filtro que impede
        -- vender item alheio informando o id.
        SELECT name, barcode, sell_price INTO v_name, v_code, v_price
          FROM public.products
         WHERE id = v_product_id AND company_id = p_company_id AND active;
        IF v_name IS NULL THEN
            RAISE EXCEPTION 'Produto não encontrado, inativo ou sem permissão: %', v_product_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;

        INSERT INTO public.sale_items (
            company_id, sale_id, product_id, product_name, product_code,
            quantity, unit_price
        ) VALUES (
            p_company_id, v_id, v_product_id, v_name, COALESCE(v_code, ''),
            v_quantity, v_price
        );

        v_bruto := v_bruto + (v_quantity * v_price);
        IF v_bruto >= 100000000 THEN
            RAISE EXCEPTION 'Total da venda acima do limite de R$ 99.999.999,99'
                USING ERRCODE = 'check_violation';
        END IF;
    END LOOP;

    v_total := v_bruto - p_discount;
    IF v_total < 0 THEN
        RAISE EXCEPTION 'Desconto (%) maior que o total dos itens (%)', p_discount, v_bruto
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.sales
       SET total = v_total, status = 'CONCLUIDA'
     WHERE id = v_id;

    RETURN v_id;
END;
$$;

-- O recibo sai da mesma transação da venda. Assim a interface mostra os
-- valores gravados mesmo quando o catálogo local está desatualizado.
CREATE OR REPLACE FUNCTION public.fn_checkout_sale(
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
    v_receipt jsonb;
BEGIN
    v_id := public.fn_create_complete_sale(
        p_company_id, p_client_id, p_items, p_payment_method, p_discount
    );
    SELECT to_jsonb(s) || jsonb_build_object('sale_items', (
        SELECT jsonb_agg(to_jsonb(i) ORDER BY i.created_on, i.id)
          FROM public.sale_items i WHERE i.sale_id = s.id
    )) INTO v_receipt FROM public.sales s WHERE s.id = v_id;
    RETURN v_receipt;
END;
$$;

-- ------------------------------------------- histórico de vendas (US17)
--
-- Consulta paginada, filtrável e ordenável. Concentrada numa função, e não
-- montada no cliente, por dois motivos: `max_rows` do PostgREST corta a
-- listagem em 1000 linhas sem avisar, e dois adaptadores (Supabase e
-- demonstração) montando filtro cada um do seu jeito divergem em silêncio.
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

-- Cancelamento de venda (US17).
--
-- A venda não deveria ter existido: as saídas dela passam a CANCELADA e o
-- trigger de recálculo devolve o saldo. É o mesmo contrato de
-- `fn_cancel_movement` -- "cancelar uma confirmada devolve o saldo" -- e a
-- guarda de `trg_protect_confirmed_movement` aceita essa transição de
-- propósito, porque só o status muda.
--
-- Nasce aqui, e não em `fn_cancel_movement`, porque aquela recusa cancelar
-- saída vinculada a venda: desfazer meia venda não é operação legítima.
CREATE OR REPLACE FUNCTION public.fn_cancel_sale(
    p_sale_id uuid,
    p_reason  text
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_status  public.sale_status;
    v_actor   uuid := public.fn_current_user_id();
    v_reason  text := btrim(COALESCE(p_reason, ''));
BEGIN
    -- A empresa sai da LINHA, nunca de parâmetro do chamador: é o padrão
    -- que `fn_update_products` estabeleceu nesta árvore.
    SELECT s.company_id, s.status INTO v_company, v_status
      FROM public.sales s WHERE s.id = p_sale_id FOR UPDATE;

    -- Venda inexistente e venda de outra empresa dão a MESMA recusa: separar
    -- as duas contaria ao chamador que o identificador existe.
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Venda não encontrada ou sem permissão para cancelar'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF v_reason = '' THEN
        RAISE EXCEPTION 'Informe o motivo do cancelamento'
            USING ERRCODE = 'check_violation';
    END IF;

    IF v_status <> 'CONCLUIDA' THEN
        RAISE EXCEPTION
            'Somente venda concluída pode ser cancelada (situação atual: %)',
            v_status USING ERRCODE = 'check_violation';
    END IF;

    -- O UNIQUE (sale_id) desta tabela é o que torna a reversão terminal; a
    -- conferência de status acima é a mensagem amigável para o caso comum.
    INSERT INTO public.sale_reversals (company_id, sale_id, kind, reason, created_by)
    VALUES (v_company, p_sale_id, 'CANCELAMENTO', v_reason, v_actor);

    UPDATE public.stock_movements
       SET status = 'CANCELADA'
     WHERE sale_id = p_sale_id AND status = 'CONFIRMADA';

    UPDATE public.sales SET status = 'CANCELADA' WHERE id = p_sale_id;

    RETURN jsonb_build_object('sale_id', p_sale_id, 'kind', 'CANCELAMENTO',
                              'reason', v_reason, 'status', 'CANCELADA');
END;
$$;

-- Devolução de venda (US17).
--
-- A venda ACONTECEU e a mercadoria voltou: a saída original continua
-- confirmada e uma ENTRADA compensatória por item devolve o saldo. Anular a
-- saída aqui apagaria do histórico de estoque que houve venda, que é
-- justamente o que distingue devolução de cancelamento.
--
-- Devolução é sempre TOTAL nesta história. A parcial exigiria itens
-- devolvidos, recálculo do total efetivo e um estado intermediário.
CREATE OR REPLACE FUNCTION public.fn_return_sale(
    p_sale_id uuid,
    p_reason  text
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_status  public.sale_status;
    v_actor   uuid := public.fn_current_user_id();
    v_reason  text := btrim(COALESCE(p_reason, ''));
    v_item    RECORD;
BEGIN
    SELECT s.company_id, s.status INTO v_company, v_status
      FROM public.sales s WHERE s.id = p_sale_id FOR UPDATE;

    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Venda não encontrada ou sem permissão para devolver'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF v_reason = '' THEN
        RAISE EXCEPTION 'Informe o motivo da devolução'
            USING ERRCODE = 'check_violation';
    END IF;

    IF v_status <> 'CONCLUIDA' THEN
        RAISE EXCEPTION
            'Somente venda concluída pode ser devolvida (situação atual: %)',
            v_status USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.sale_reversals (company_id, sale_id, kind, reason, created_by)
    VALUES (v_company, p_sale_id, 'DEVOLUCAO', v_reason, v_actor);

    FOR v_item IN
        SELECT i.product_id, i.quantity
          FROM public.sale_items i
         WHERE i.sale_id = p_sale_id AND i.product_id IS NOT NULL
         -- Mesma ordem de bloqueio da conclusão da venda (triggers/06), para
         -- que duas operações concorrentes sobre os mesmos produtos não se
         -- cruzem em sentidos opostos.
         ORDER BY i.product_id, i.id
    LOOP
        INSERT INTO public.stock_movements (
            company_id, product_id, sale_id, kind, quantity, status,
            note, created_by, confirmed_on
        ) VALUES (
            v_company, v_item.product_id, p_sale_id, 'ENTRADA',
            v_item.quantity, 'CONFIRMADA',
            'DEVOLUCAO_VENDA - venda ' || p_sale_id::text, v_actor, now()
        );
    END LOOP;

    UPDATE public.sales SET status = 'DEVOLVIDA' WHERE id = p_sale_id;

    RETURN jsonb_build_object('sale_id', p_sale_id, 'kind', 'DEVOLUCAO',
                              'reason', v_reason, 'status', 'DEVOLVIDA');
END;
$$;
