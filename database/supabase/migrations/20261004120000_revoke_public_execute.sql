-- Fecha o EXECUTE que ficou aberto para PUBLIC em funções criadas DEPOIS da
-- migration de segurança.
--
-- O BURACO, E POR QUE ELE EXISTIU
--
-- `20261003120100_policies_security.sql` fecha tudo com uma varredura:
-- percorre `pg_proc` revogando EXECUTE de PUBLIC/anon/authenticated e reabre
-- só a allowlist. Essa varredura enxerga as funções que existiam NAQUELE
-- momento.
--
-- `fn_update_products` nasceu em `20261003120200_fn_update_products.sql` — cem
-- unidades de timestamp DEPOIS. No Postgres, função nova nasce com EXECUTE
-- concedido a PUBLIC, e a varredura já tinha passado. Resultado medido contra
-- o projeto real: de todas as funções do catálogo, `fn_update_products` era a
-- única que o anônimo conseguia chamar.
--
-- O ESTRAGO FOI LIMITADO, E NÃO POR SORTE
--
-- A função é SECURITY DEFINER mas checa `fn_has_role` antes de qualquer
-- gravação, e `fn_current_user_id()` devolve NULL para quem não tem sessão.
-- O anônimo executava o corpo e levava 'Produto não encontrado ou sem
-- permissão' — sem ler nem escrever nada. A defesa em profundidade funcionou;
-- o que falhou foi a camada de fora, e é ela que esta migration repõe.
--
-- `ALTER DEFAULT PRIVILEGES` não resolveria sozinho: ele vale por papel
-- criador e só para objetos criados DEPOIS de ser declarado, então uma
-- migration aplicada por outro papel reabriria o mesmo buraco.

-- =================================================== 1. fechar tudo de novo

DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT p.oid::regprocedure AS sig
             FROM pg_proc p
             JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.prokind = 'f'
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon', r.sig);
  END LOOP;
END $$;

-- ================================================== 2. reabrir a allowlist
--
-- Mesma lista das migrations anteriores, acrescida das funções do diretório
-- de usuários. O REVOKE acima tira de PUBLIC e anon, mas também é a rede de
-- segurança caso alguma função tenha perdido o grant no caminho.

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
      EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO app_backend, authenticated', v_sig);
      v_found := true;
    END LOOP;
    IF NOT v_found THEN v_missing := v_missing || v_name; END IF;
  END LOOP;

  -- Falha alto: função da allowlist que não existe significa migration
  -- faltando, e deixar passar entregaria uma aplicação sem permissão só
  -- descoberta em runtime.
  IF array_length(v_missing, 1) > 0 THEN
    RAISE EXCEPTION 'Funções obrigatórias ausentes: %', array_to_string(v_missing, ', ');
  END IF;
END $$;

-- ============================================== 3. impedir a repetição
--
-- Para funções criadas daqui em diante PELO PAPEL QUE APLICA ESTA MIGRATION.
-- Não cobre outro papel criador — por isso a varredura do passo 1 continua
-- sendo o que realmente garante o fechamento, e deve ser repetida por
-- qualquer migration futura que crie função nova.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon;

-- ================================================ 4. conferência obrigatória
--
-- Se sobrar qualquer função com EXECUTE para PUBLIC ou anon, esta migration
-- falha em vez de se declarar bem-sucedida.
DO $$
DECLARE
  v_abertas text;
BEGIN
  SELECT string_agg(DISTINCT p.proname, ', ')
    INTO v_abertas
    FROM pg_proc p
    CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) acl
   WHERE p.pronamespace = 'public'::regnamespace
     AND p.prokind = 'f'
     AND acl.privilege_type = 'EXECUTE'
     AND (acl.grantee = 0 OR pg_get_userbyid(acl.grantee) = 'anon');

  IF v_abertas IS NOT NULL THEN
    RAISE EXCEPTION 'Ainda executáveis por PUBLIC/anon: %', v_abertas;
  END IF;
END $$;
