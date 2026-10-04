-- Identidade por JWT do Supabase Auth, para que a aplicação desktop alcance
-- o banco sem carregar credencial de role de banco.
--
-- POR QUE ESTA MIGRATION EXISTE
--
-- O modelo de 01_security.sql foi desenhado para um BACKEND que é dono da
-- conexão: ele entra como `app_backend` e faz `SET app.user_id = <uuid>`
-- depois do login, que é o que `fn_current_user_id()` lê. O StockFlow não é
-- esse backend — é um desktop PySide6 falando o REST do Supabase com a chave
-- publicável, e por ali:
--
--   1. a role é `anon`/`authenticated`, e o REVOKE de 01_security.sql tirou
--      TODO privilégio das duas: qualquer leitura devolve
--      "permission denied for table products";
--   2. não existe caminho para `SET app.user_id` — cada request pega uma
--      conexão do pool e o REST não expõe `SET`. Mesmo com os grants,
--      `fn_current_user_id()` devolveria NULL, `fn_has_role()` daria false e
--      toda gravação morreria em "Sem permissão ... nesta empresa".
--
-- O que muda aqui: a identidade passa a poder vir do JWT (`auth.uid()`), e os
-- privilégios da aplicação passam a valer também para `authenticated`.
--
-- O QUE ESTA MIGRATION NÃO FAZ
--
-- Não remove nada. `app_backend` continua com os mesmos grants e o caminho do
-- GUC continua funcionando — um backend futuro não precisa ser reescrito. As
-- contas também não são migradas: `user_accounts.pass_hash` segue lá, e
-- `fn_get_login_credentials` continua válida para quem ainda usar o login
-- próprio. A ponte é opcional e por linha, via `auth_user_id`.

-- --------------------------------------------------------------- identidade

-- Ponte entre a conta do Supabase Auth e a conta de domínio.
--
-- Coluna nova em vez de reaproveitar `user_accounts.id = auth.users.id`:
-- igualar os ids exigiria recriar as contas existentes, e `company_users`
-- aponta para elas. Assim a adoção é por usuário e sem perda de dado.
--
-- Sem chave estrangeira para `auth.users` de propósito: além de `auth` ser
-- schema gerido pelo Supabase, a checagem estática de migrations
-- (tests/test_database_migrations.py, teste de dependências fora de ordem)
-- cobra que toda tabela apontada por uma FK tenha sido criada por uma
-- migration desta árvore — e `auth.users` nunca é. O índice único abaixo é o
-- que a resolução de identidade precisa.
ALTER TABLE public.user_accounts
  ADD COLUMN IF NOT EXISTS auth_user_id uuid;

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_accounts_auth_user
  ON public.user_accounts (auth_user_id)
  WHERE auth_user_id IS NOT NULL;

-- Resolve o usuário corrente por DOIS caminhos, nesta ordem:
--
--   1. JWT: `auth.uid()` é o id em `auth.users`; traduzido para o id de
--      domínio por `auth_user_id`, que é o que `company_users` referencia.
--   2. GUC `app.user_id`: o caminho original, de um backend dono da conexão.
--
-- A ordem importa. O JWT é a identidade provada pelo Supabase; o GUC é um
-- parâmetro de sessão que só quem já tem a conexão consegue definir. Se o GUC
-- viesse primeiro, uma sessão autenticada que por acaso tivesse o parâmetro
-- definido responderia pelo outro usuário.
--
-- Continua STABLE e SECURITY DEFINER: ela lê `user_accounts`, que não tem
-- GRANT de SELECT para ninguém — o acesso àquela tabela é sempre por função.
CREATE OR REPLACE FUNCTION public.fn_current_user_id()
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, extensions AS $$
    SELECT COALESCE(
        (SELECT ua.id
           FROM public.user_accounts ua
          WHERE ua.auth_user_id = auth.uid()),
        NULLIF(current_setting('app.user_id', true), '')::uuid
    );
$$;

-- ------------------------------------------------------------- privilégios

-- Leitura direta onde já existe policy que escopa por empresa. Mesma lista
-- dada a `app_backend` em 01_security.sql: `user_accounts` e `company_users`
-- continuam de fora, alcançáveis só pelas funções SECURITY DEFINER.
GRANT SELECT ON public.company,
                public.categories,
                public.products,
                public.product_stock,
                public.vw_stock_situation
  TO authenticated;

-- As policies de SELECT existentes são `TO app_backend`, e policy é por role:
-- sem uma policy própria, `authenticated` passaria no GRANT e pararia na RLS,
-- vendo zero linhas. O predicado é o MESMO (`fn_is_member`), para que as duas
-- roles enxerguem exatamente o mesmo recorte — duas regras diferentes para o
-- mesmo dado divergem com o tempo.
DROP POLICY IF EXISTS company_select_authenticated       ON public.company;
DROP POLICY IF EXISTS categories_select_authenticated    ON public.categories;
DROP POLICY IF EXISTS products_select_authenticated      ON public.products;
DROP POLICY IF EXISTS product_stock_select_authenticated ON public.product_stock;

CREATE POLICY company_select_authenticated ON public.company
  FOR SELECT TO authenticated USING (public.fn_is_member(id));

CREATE POLICY categories_select_authenticated ON public.categories
  FOR SELECT TO authenticated USING (public.fn_is_member(company_id));

CREATE POLICY products_select_authenticated ON public.products
  FOR SELECT TO authenticated USING (public.fn_is_member(company_id));

CREATE POLICY product_stock_select_authenticated ON public.product_stock
  FOR SELECT TO authenticated USING (EXISTS (
    SELECT 1 FROM public.products p WHERE p.id = product_stock.product_id
  ));

-- --------------------------------------------------- execute nas funções

-- Mesma allowlist de 01_security.sql, acrescida de `fn_my_companies`: depois
-- do login a aplicação precisa descobrir a empresa e o papel do usuário, e
-- sem ela não há como montar a sessão nem preencher `p_company_id` nas
-- chamadas de catálogo.
--
-- O RAISE no fim é o mesmo contrato do arquivo original: função da lista que
-- sumir num refactor faz a migration falhar alto, em vez de deixar a
-- aplicação sem permissão só em runtime.
DO $$
DECLARE
  v_names text[] := ARRAY[
    'fn_get_login_credentials', 'fn_register_company', 'fn_set_own_pass_hash',
    'fn_create_company_user', 'fn_update_company_user', 'fn_toggle_company_user',
    'fn_list_company_users', 'fn_create_categories', 'fn_create_products',
    'fn_update_products', 'fn_set_product_active',
    'fn_set_min_stock', 'fn_set_min_stock_batch',
    'fn_stock_panel', 'fn_company_stock_state',
    'fn_current_user_id', 'fn_has_role', 'fn_is_member', 'fn_stock_state',
    'fn_my_companies'
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
      EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO authenticated', v_sig);
      -- fn_my_companies não estava na allowlist original; sem isto o
      -- backend continuaria sem conseguir resolver a empresa do usuário.
      EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO app_backend', v_sig);
      v_found := true;
    END LOOP;
    IF NOT v_found THEN v_missing := v_missing || v_name; END IF;
  END LOOP;

  IF array_length(v_missing, 1) > 0 THEN
    RAISE EXCEPTION 'Funções obrigatórias ausentes: %', array_to_string(v_missing, ', ');
  END IF;
END $$;

-- ------------------------------------------------------------- adoção
--
-- Esta migration não cria nenhum usuário. Para ligar uma conta do Supabase
-- Auth a uma conta de domínio já existente, rode você mesmo, uma vez por
-- usuário (o e-mail é o do Supabase Auth; o login é `user_accounts.name`):
--
--   UPDATE public.user_accounts ua
--      SET auth_user_id = au.id
--     FROM auth.users au
--    WHERE au.email = 'ana.ferreira@example.com'
--      AND ua.name  = 'ana.ferreira';
--
-- Confira antes de confiar na sessão: sem o vínculo, `fn_current_user_id()`
-- devolve NULL e TODA chamada de catálogo é recusada por falta de papel —
-- que é a falha fechada correta, mas parece "permissão quebrada" na tela.
--
--   SELECT ua.name, ua.auth_user_id, cu.company_id, cu.role
--     FROM public.user_accounts ua
--     JOIN public.company_users cu ON cu.user_account_id = ua.id
--    WHERE ua.auth_user_id IS NOT NULL;
