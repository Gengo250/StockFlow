ALTER TABLE public.company        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_accounts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.company_users  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_stock  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.register       ENABLE ROW LEVEL SECURITY;

-- 2. Reset de Permissões Globais
-- Removemos todos os acessos iniciais para aplicar apenas o que é estritamente necessário
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUthenticated;

-- 3. Permissões de Leitura Básica (GRANT SELECT)
-- Permite que a role 'anon' tente ler as tabelas, mas o RLS filtrará as linhas
GRANT SELECT ON public.company, public.categories, public.products,
                public.product_stock, public.register, public.vw_stock_//situation TO anon;

-- 4. POLÍTICAS DE ACESSO (RLS POLICIES)

-- A: Acesso a Empresas (Apenas empresas onde o usuário é membro)
CREATE POLICY company_select ON public.company FOR SELECT TO anon
    USING (id IN (SELECT public.fn_my_companies()));

-- B: Acesso a Categorias (Filtrado pela empresa do usuário)
CREATE POLICY categories_select ON public.categories FOR SELECT TO anon
    USING (company_id IN (SELECT public.fn_my_companies()));

-- C: Acesso a Produtos (Filtrados pela empresa do usuário)
CREATE POLICY products_select ON public.products FOR SELECT TO anon
    USING (company_id IN (SELECT public.fn_my_companies()));

-- D: Acesso ao Estoque Mínimo (Herda a segurança da tabela de produtos)
CREATE POLICY product_stock_select ON public.product_stock FOR SELECT TO anon
    USING (EXISTS (SELECT 1 FROM public.products p WHERE p.id = product_stock.product_id));

-- E: Acesso aos Logs de Caixa (Tabela 'register')
-- Como a tabela register não tem company_id, validamos se o usuário está autenticado no sistema
CREATE POLICY register_select ON public.register FOR SELECT TO anon
    USING (public.fn_current_user_id() IS NOT NULL);

-- 5. Limpeza de Permissões de Funções
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT p.oid::regprocedure AS sig
               FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
              WHERE n.nspname = 'public' AND p.prokind = 'f'
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated', r.sig);
    END LOOP;
END $$;

-- 6. Concessão de Execução (GRANT EXECUTE)
-- Definimos exatamente quais funções o Frontend pode chamar v

GRANT EXECUTE ON FUNCTION
    public.fn_my_companies(),
    public.fn_change_own_password(text, text),
    public.fn_create_company_user(uuid, text, text, public.user_role),
    public.fn_update_company_user(uuid, uuid, text, public.user_role, boolean, text),
    public.fn_toggle_company_user(uuid, uuid, boolean),
    public.fn_list_company_users(uuid),
    public.fn_create_category(uuid, text),
    public.fn_create_product(uuid, text, text, numeric, numeric, public.unit_enum, integer, text),
    public.fn_set_product_active(uuid, boolean),
    public.fn_set_min_stock(uuid, integer),
    public.fn_set_min_stock_batch(jsonb),
    public.fn_stock_panel(uuid),
    public.fn_company_stock_state(uuid)
TO anon;

GRANT EXECUTE ON FUNCTION
    public.fn_current_user_id(),
    public.fn_has_role(uuid, public.user_//role[]),
    public.fn_is_member(uuid),
    public.fn_stock_state(integer, integer)
TO anon;

GRANT EXECUTE ON FUNCTION public.fn_bootstrap_company(text, tele;