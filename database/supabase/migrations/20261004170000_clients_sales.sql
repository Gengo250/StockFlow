-- US07: company-scoped clients and sales with historical snapshots.
-- Generated from database/code and reviewed locally; not applied remotely.

-- Clientes e vendas. Depende de company (01_identity) e products (03_catalog).

CREATE OR REPLACE FUNCTION public.fn_valid_br_document(p_document text)
RETURNS boolean
LANGUAGE plpgsql IMMUTABLE STRICT
SET search_path = public AS $$
DECLARE
    v_digits text := p_document;
    v_sum integer;
    v_remainder integer;
    v_first integer;
    v_second integer;
    i integer;
    v_weight integer;
BEGIN
    IF v_digits !~ '^[0-9]+$' OR v_digits IN (
        '00000000000', '11111111111', '22222222222', '33333333333',
        '44444444444', '55555555555', '66666666666', '77777777777',
        '88888888888', '99999999999',
        '00000000000000', '11111111111111', '22222222222222',
        '33333333333333', '44444444444444', '55555555555555',
        '66666666666666', '77777777777777', '88888888888888',
        '99999999999999'
    ) THEN
        RETURN false;
    END IF;

    IF length(v_digits) = 11 THEN
        v_sum := 0;
        FOR i IN 1..9 LOOP
            v_sum := v_sum + substring(v_digits, i, 1)::integer * (11 - i);
        END LOOP;
        v_remainder := v_sum % 11;
        v_first := CASE WHEN v_remainder < 2 THEN 0 ELSE 11 - v_remainder END;

        v_sum := 0;
        FOR i IN 1..10 LOOP
            v_weight := CASE WHEN i = 10 THEN 2 ELSE 12 - i END;
            v_sum := v_sum + substring(v_digits, i, 1)::integer * v_weight;
        END LOOP;
        v_remainder := v_sum % 11;
        v_second := CASE WHEN v_remainder < 2 THEN 0 ELSE 11 - v_remainder END;
        RETURN substring(v_digits, 10, 2) = (v_first::text || v_second::text);
    ELSIF length(v_digits) = 14 THEN
        v_sum := 0;
        FOR i IN 1..12 LOOP
            v_weight := CASE WHEN i <= 4 THEN 6 - i ELSE 14 - i END;
            v_sum := v_sum + substring(v_digits, i, 1)::integer * v_weight;
        END LOOP;
        v_remainder := v_sum % 11;
        v_first := CASE WHEN v_remainder < 2 THEN 0 ELSE 11 - v_remainder END;

        v_sum := 0;
        FOR i IN 1..13 LOOP
            v_weight := CASE WHEN i <= 5 THEN 7 - i ELSE 15 - i END;
            v_sum := v_sum + substring(v_digits, i, 1)::integer * v_weight;
        END LOOP;
        v_remainder := v_sum % 11;
        v_second := CASE WHEN v_remainder < 2 THEN 0 ELSE 11 - v_remainder END;
        RETURN substring(v_digits, 13, 2) = (v_first::text || v_second::text);
    END IF;

    RETURN false;
END;
$$;

CREATE TABLE public.clients (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    name         text NOT NULL CHECK (btrim(name) <> ''),
    document     text,
    email        text NOT NULL DEFAULT ''
                 CHECK (email = '' OR email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
    phone        text NOT NULL DEFAULT ''
                 CHECK (phone = '' OR (
                        phone ~ '^[+0-9().[:space:]-]+$' AND
                        length(regexp_replace(phone, '\D', '', 'g')) IN (10, 11))),
    notes        text NOT NULL DEFAULT '',
    active       boolean NOT NULL DEFAULT true,
    created_on   timestamptz NOT NULL DEFAULT now(),
    updated_on   timestamptz NOT NULL DEFAULT now(),
    CHECK (document IS NULL OR
           (document <> '' AND public.fn_valid_br_document(document))),
    UNIQUE (company_id, id)
);

-- Documentos são armazenados apenas com dígitos pela aplicação; NULL/'' não
-- participam da unicidade, mas documentos iguais não podem ser duplicados
-- nem por chamadas concorrentes.
CREATE UNIQUE INDEX uq_clients_company_document
    ON public.clients (company_id, document)
    WHERE document IS NOT NULL AND document <> '';
CREATE INDEX idx_clients_company_name
    ON public.clients (company_id, lower(name));

CREATE TABLE public.sales (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    client_id        uuid NOT NULL,
    product_id       uuid,
    client_name      text NOT NULL,
    product_name     text NOT NULL,
    product_code     text NOT NULL,
    total            numeric(10,2) NOT NULL CHECK (total >= 0),
    created_by       uuid,
    created_on       timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, client_id)
        REFERENCES public.clients (company_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (product_id)
        REFERENCES public.products (id) ON DELETE SET NULL
);
CREATE INDEX idx_sales_company_created
    ON public.sales (company_id, created_on DESC);


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


CREATE TRIGGER trg_clients_updated BEFORE UPDATE ON public.clients
    FOR EACH ROW EXECUTE FUNCTION public.trg_set_updated_on();

-- Modelo de segurança: role de aplicação, RLS e grants.
-- Portado de database/archive/policies/setup_security.sql (branch
-- companies_user_stock_configure, PR #9), adaptado ao schema desta árvore.
--
-- Vem por último em schema_paths: depende das tabelas (01-04), das funções de
-- autorização (02_authz) e da view de estoque (views/01).

-- Role sem login: a aplicação se conecta como ela, nunca como owner.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
    CREATE ROLE app_backend NOLOGIN NOINHERIT;
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO app_backend;

-- ------------------------------------------------------------------ RLS

ALTER TABLE public.company        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_accounts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.company_users  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_stock  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stock_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clients        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales           ENABLE ROW LEVEL SECURITY;

-- register não tem coluna de empresa (tables/02_cash_register.sql: "Caixa.
-- Independente das demais tabelas."), então não há como escopar por tenant.
-- RLS fica habilitada sem policy — nega tudo por padrão para quem não é owner
-- — e nenhum GRANT SELECT é dado. Ver nota no fim do arquivo.
ALTER TABLE public.register       ENABLE ROW LEVEL SECURITY;

-- access_register fica DE FORA de propósito: pr_validate_login
-- (procedures/06_cash_register.sql) não é SECURITY DEFINER e lê essa tabela
-- como invoker. Habilitar RLS aqui faria todo login do caixa cair em
-- NO_DATA_FOUND e retornar is_valid = FALSE silenciosamente.

-- -------------------------------------------------------------- privilégios

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, anon, authenticated, app_backend;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL     ON TABLES    FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

-- Leitura direta só onde existe policy que escopa por empresa.
-- user_accounts e company_users ficam sem SELECT: o acesso a eles passa
-- obrigatoriamente pelas funções SECURITY DEFINER (fn_list_company_users etc).
--
-- `authenticated` entra junto com `app_backend` porque existem DOIS clientes
-- legítimos do mesmo recorte: um backend dono da conexão (identidade pelo GUC
-- `app.user_id`) e o app desktop falando REST (identidade pelo JWT). Quem
-- separa um do outro é `fn_current_user_id()`, não o privilégio.
GRANT SELECT ON public.company,
                public.categories,
                public.products,
                public.product_stock,
                public.stock_movements,
                public.clients,
                public.sales,
                public.vw_stock_situation,
                public.vw_stock_alerts
  TO app_backend, authenticated;

-- ----------------------------------------------------------------- policies

DROP POLICY IF EXISTS company_select       ON public.company;
DROP POLICY IF EXISTS categories_select    ON public.categories;
DROP POLICY IF EXISTS products_select      ON public.products;
DROP POLICY IF EXISTS product_stock_select ON public.product_stock;
DROP POLICY IF EXISTS stock_movements_select ON public.stock_movements;
DROP POLICY IF EXISTS clients_select          ON public.clients;
DROP POLICY IF EXISTS sales_select            ON public.sales;

-- Policy é por role: o GRANT acima deixa `authenticated` chegar à tabela, mas
-- sem aparecer no TO da policy ela veria zero linha. O predicado é o MESMO
-- para as duas roles de propósito — duas regras para o mesmo dado divergem.
CREATE POLICY company_select ON public.company FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(id));

CREATE POLICY categories_select ON public.categories FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

CREATE POLICY products_select ON public.products FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

-- product_stock não tem company_id; herda o escopo via products, que já tem
-- a sua própria policy aplicada nesta mesma subconsulta.
-- stock_movements tem company_id próprio (duplicado de products de
-- propósito): a policy escopa direto, sem entrar no catálogo a cada linha.
CREATE POLICY stock_movements_select ON public.stock_movements
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

CREATE POLICY clients_select ON public.clients
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

CREATE POLICY sales_select ON public.sales
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

CREATE POLICY product_stock_select ON public.product_stock
  FOR SELECT TO app_backend, authenticated
  USING (EXISTS (
    SELECT 1 FROM public.products p WHERE p.id = product_stock.product_id
  ));

-- ------------------------------------------------------ execute nas funções

-- Fecha tudo primeiro: função nova que alguém adicionar não nasce pública.
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT p.oid::regprocedure AS sig
             FROM pg_proc p
             JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.prokind = 'f'
  LOOP
    EXECUTE format(
      'REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated, app_backend', r.sig);
  END LOOP;
END $$;

-- Reabre só a superfície pública da aplicação. O RAISE no fim é proposital:
-- se uma função da lista sumir num refactor, a migration falha alto em vez de
-- deixar a aplicação sem permissão em runtime.
DO $$
DECLARE
  v_names text[] := ARRAY[
    'fn_get_login_credentials', 'fn_register_company', 'fn_set_own_pass_hash',
    'fn_create_company_user', 'fn_update_company_user', 'fn_toggle_company_user',
    'fn_list_company_users', 'fn_set_company_user_department',
    'fn_create_categories', 'fn_create_products',
    'fn_update_products', 'fn_set_product_active',
    'fn_set_min_stock', 'fn_set_min_stock_batch',
    'fn_stock_panel', 'fn_company_stock_state',
    -- auxiliares usadas pelas policies e pela view
    'fn_current_user_id', 'fn_has_role', 'fn_is_member', 'fn_stock_state',
    -- Depois do login a aplicação precisa descobrir empresa e papel do
    -- usuário para montar a sessão e preencher `p_company_id` nas chamadas
    -- de catálogo. Sem esta, não há como sair da tela de login.
    'fn_my_companies',
    -- Movimentações (US03): o saldo é a soma das confirmadas.
    'fn_register_movement', 'fn_confirm_movement', 'fn_cancel_movement',
    'fn_confirmed_balance',
    'fn_list_company_clients', 'fn_create_client', 'fn_update_client',
    'fn_set_client_active', 'fn_register_sale'
  ];
  v_name    text;
  v_sig     regprocedure;
  v_found   boolean;
  v_missing text[] := '{}';
BEGIN
  FOREACH v_name IN ARRAY v_names LOOP
    v_found := false;
    FOR v_sig IN SELECT p.oid::regprocedure FROM pg_proc p
                  WHERE p.pronamespace = 'public'::regnamespace AND p.proname = v_name
    LOOP
      EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO app_backend, authenticated', v_sig);
      v_found := true;
    END LOOP;
    IF NOT v_found THEN v_missing := v_missing || v_name; END IF;
  END LOOP;

  IF array_length(v_missing, 1) > 0 THEN
    RAISE EXCEPTION 'Funções obrigatórias ausentes: %', array_to_string(v_missing, ', ');
  END IF;
END $$;

-- Para funções criadas daqui em diante PELO PAPEL que aplica este arquivo.
-- Não cobre outro papel criador, e por isso NÃO substitui a varredura de
-- REVOKE acima: toda migration que criar função nova precisa repetir a
-- varredura. Foi exatamente esse o buraco de `fn_update_products`, criada por
-- uma migration posterior à de segurança e por isso nascida com EXECUTE para
-- PUBLIC — o anônimo conseguia chamá-la (e levava recusa de `fn_has_role`,
-- mas a camada de fora não deveria nem ter deixado chegar lá).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon;

-- PENDENTE: register/access_register não têm vínculo com company. Enquanto
-- isso não for resolvido, o caixa não é isolável por empresa e o backend não
-- lê essas tabelas via app_backend.
