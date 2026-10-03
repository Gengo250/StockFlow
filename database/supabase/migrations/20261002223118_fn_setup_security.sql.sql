DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        CREATE ROLE app_backend NOLOGIN NOINHERIT;
    END IF;
END $$;
GRANT USAGE ON SCHEMA public TO app_backend;
 

ALTER TABLE public.company        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_accounts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.company_users  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_stock  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.register       ENABLE ROW LEVEL SECURITY;
 

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, anon, authenticated, app_backend;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;
 

GRANT SELECT ON public.company, public.categories, public.products,
                public.product_stock, public.register, public.vw_stock_situation TO app_backend;
 
DROP POLICY IF EXISTS company_select       ON public.company;
DROP POLICY IF EXISTS categories_select    ON public.categories;
DROP POLICY IF EXISTS products_select      ON public.products;
DROP POLICY IF EXISTS product_stock_select ON public.product_stock;
DROP POLICY IF EXISTS register_select      ON public.register;
 
CREATE POLICY company_select ON public.company FOR SELECT TO app_backend
    USING (public.fn_is_member(id));
 
CREATE POLICY categories_select ON public.categories FOR SELECT TO app_backend
    USING (public.fn_is_member(company_id));
 
CREATE POLICY products_select ON public.products FOR SELECT TO app_backend
    USING (public.fn_is_member(company_id));
 

CREATE POLICY product_stock_select ON public.product_stock FOR SELECT TO app_backend
    USING (EXISTS (SELECT 1 FROM public.products p WHERE p.id = product_stock.product_id));
 

CREATE POLICY register_select ON public.register FOR SELECT TO app_backend
    USING (public.fn_has_role(company_id, ARRAY['ADMIN','SELLER']::public.user_role[]));
 

DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT p.oid::regprocedure AS sig
               FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
              WHERE n.nspname = 'public' AND p.prokind = 'f'
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated, app_backend', r.sig);
    END LOOP;
END $$;


DO $$
DECLARE
    v_names text[] := ARRAY[
        'fn_get_login_credentials', 'fn_register_company', 'fn_set_own_pass_hash',
        'fn_create_company_user', 'fn_update_company_user', 'fn_toggle_company_user',
        'fn_list_company_users', 'fn_create_category', 'fn_create_product',
        'fn_set_product_active', 'fn_set_min_stock', 'fn_set_min_stock_batch',
        'fn_stock_panel', 'fn_company_stock_state',
        -- auxiliares usadas pelas policies e pela view
        'fn_current_user_id', 'fn_has_role', 'fn_is_member', 'fn_stock_state'
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
            EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO app_backend', v_sig);
            v_found := true;
        END LOOP;
        IF NOT v_found THEN v_missing := v_missing || v_name; END IF;
    END LOOP;
 
    IF array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION 'Funções obrigatórias ausentes (aplique as migrations de user/ e stock/ antes): %',
            array_to_string(v_missing, ', ');
    END IF;
END $$;
 

 