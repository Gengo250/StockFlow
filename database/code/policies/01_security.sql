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
ALTER TABLE public.sale_items      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_log       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.suppliers       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.role_change_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_edit_log  ENABLE ROW LEVEL SECURITY;

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
                public.suppliers,
                public.sales,
                public.sale_items,
                public.sales_log,
                public.role_change_log,
                public.price_edit_log,
                public.vw_stock_situation,
                public.vw_stock_alerts
  TO app_backend, authenticated;

-- SELECT, e só. O log de permissões (H14) é escrito exclusivamente pelo
-- trigger `trg_company_users_log_role`, que é SECURITY DEFINER e alcança a
-- tabela como dono. Dar INSERT/UPDATE/DELETE aqui permitiria ao sistema
-- auditado reescrever a própria auditoria.

-- ----------------------------------------------------------------- policies

DROP POLICY IF EXISTS company_select       ON public.company;
DROP POLICY IF EXISTS categories_select    ON public.categories;
DROP POLICY IF EXISTS products_select      ON public.products;
DROP POLICY IF EXISTS product_stock_select ON public.product_stock;
DROP POLICY IF EXISTS stock_movements_select ON public.stock_movements;
DROP POLICY IF EXISTS clients_select          ON public.clients;
DROP POLICY IF EXISTS sales_select            ON public.sales;
DROP POLICY IF EXISTS sale_items_select        ON public.sale_items;
DROP POLICY IF EXISTS sales_log_select         ON public.sales_log;
DROP POLICY IF EXISTS suppliers_select        ON public.suppliers;
DROP POLICY IF EXISTS role_change_log_select  ON public.role_change_log;
DROP POLICY IF EXISTS price_edit_log_select   ON public.price_edit_log;

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

-- sale_items e sales_log repetem company_id pela mesma razão de
-- stock_movements: escopar por coluna própria evita entrar em `sales` a cada
-- linha lida do histórico de vendas.
CREATE POLICY sale_items_select ON public.sale_items
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

CREATE POLICY sales_log_select ON public.sales_log
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

CREATE POLICY suppliers_select ON public.suppliers
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_has_role(company_id, ARRAY['ADMIN','STOCK']::public.user_role[]));

-- Quem lê a auditoria de permissões é só o ADMIN da própria empresa — a
-- mesma alçada de `fn_list_company_users`, porque o log diz exatamente quem
-- recebeu qual acesso e quando.
CREATE POLICY role_change_log_select ON public.role_change_log
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[]));

CREATE POLICY price_edit_log_select ON public.price_edit_log
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[]));

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
    'fn_register_adjustment',
    'fn_confirmed_balance',
    'fn_list_company_clients', 'fn_create_client', 'fn_update_client',
    'fn_set_client_active', 'fn_register_sale',
    -- Venda com vários itens, desconto e forma de pagamento (US10) e edição
    -- de estoque por código de barras (US09).
    'fn_create_complete_sale', 'fn_checkout_sale', 'fn_edit_product_stock',
    'fn_list_company_suppliers', 'fn_create_supplier', 'fn_update_supplier',
    'fn_set_supplier_active', 'fn_set_product_supplier',
    'fn_register_supplier_movement', 'fn_save_product', 'fn_save_company_member',
    -- Histórico cronológico de preço e custo (H09). Só leitura, e só do ADMIN:
    -- a própria função repete a alçada de `price_edit_log_select`, porque
    -- SECURITY DEFINER passa por cima da RLS que protege a tabela.
    'fn_list_price_edits'
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
