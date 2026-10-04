-- Diretório de usuários: os campos que a tela de Usuários já mostra passam a
-- existir no banco.
--
-- A tela lista nome, login, DEPARTAMENTO, perfil, status e ÚLTIMO ACESSO, mas
-- `company_users` só tinha `role`, `active` e datas. Enquanto a tela foi
-- alimentada por `presentation/demo_data.py` isso não incomodou; para ligá-la
-- ao banco, as duas colunas que faltam precisam de origem real.
--
-- DUAS ORIGENS DIFERENTES, DE PROPÓSITO:
--
--   departamento -> coluna nova em `company_users`. É atributo do vínculo,
--       não da pessoa: o mesmo usuário pode ser "Estoque" numa empresa e
--       "Compras" em outra, e guardá-lo em `user_accounts` forçaria um valor
--       só para todas.
--
--   último acesso -> DERIVADO de `auth.users.last_sign_in_at`, sem coluna
--       nova. O Supabase Auth já registra isso a cada login, e é dado que
--       ninguém precisa manter sincronizado. Uma coluna própria exigiria a
--       aplicação gravar a cada entrada — mais uma escrita no caminho do
--       login, que erraria para quem tem acesso a duas empresas e ficaria
--       desatualizada em todo login que não passasse pela nossa UI.

-- ============================================================= departamento

ALTER TABLE public.company_users
  ADD COLUMN IF NOT EXISTS department text;

-- ===================================================== acesso ao schema auth
--
-- `fn_list_company_users` passa a ler `auth.users`. A função é SECURITY
-- DEFINER e roda com o dono dela (o papel que aplica esta migration), que no
-- Supabase alcança o schema `auth`. Se não alcançar, é melhor descobrir AGORA,
-- na migration, do que como erro em runtime ao abrir a tela de Usuários.
DO $$
BEGIN
  PERFORM 1 FROM auth.users LIMIT 1;
EXCEPTION WHEN insufficient_privilege THEN
  RAISE EXCEPTION
    'O dono desta migration não consegue ler auth.users, e '
    'fn_list_company_users depende disso para o último acesso. '
    'Aplique a migration com um papel que alcance o schema auth.';
END $$;

-- ================================================ listagem para a tela
--
-- DROP antes de CREATE: a assinatura de retorno muda, e `CREATE OR REPLACE`
-- não altera o tipo de retorno de uma função existente — ele falharia com
-- "cannot change return type of existing function". O GRANT é refeito no fim
-- porque o DROP leva as permissões junto.
DROP FUNCTION IF EXISTS public.fn_list_company_users(uuid);

CREATE OR REPLACE FUNCTION public.fn_list_company_users(p_company_id uuid)
RETURNS TABLE (
    user_id      uuid,
    login        text,
    display_name text,
    department   text,
    user_role    public.user_role,
    is_active    boolean,
    last_access  timestamptz,
    created_on   timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF NOT public.fn_is_admin(public.fn_current_user_id(), p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem listar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN QUERY
    SELECT
        ua.id,
        -- O e-mail do Auth é o que a tela chama de "login" e o que o usuário
        -- digita para entrar. `user_accounts.name` é o login LOCAL (minúsculo,
        -- sem espaço) e só aparece enquanto a conta não foi vinculada.
        COALESCE(au.email, ua.name),
        -- Nome de exibição: metadado do Auth, com o login local como último
        -- recurso. `user_accounts.name` tem CHECK de minúsculo, então ele
        -- nunca é um nome próprio bem formatado.
        COALESCE(
            NULLIF(btrim(au.raw_user_meta_data->>'name'), ''),
            NULLIF(btrim(au.raw_user_meta_data->>'full_name'), ''),
            ua.name
        ),
        cd.department,
        cd.role,
        cd.active,
        au.last_sign_in_at,
        cd.created_on
      FROM public.company_users cd
      JOIN public.user_accounts ua ON ua.id = cd.user_account_id
      -- Junção pela esquerda: conta ainda não vinculada ao Auth continua
      -- aparecendo na lista, sem e-mail e sem último acesso. Escondê-la
      -- deixaria o administrador sem ver exatamente quem precisa de
      -- providência.
      LEFT JOIN auth.users au ON au.id = ua.auth_user_id
     WHERE cd.company_id = p_company_id
     ORDER BY 3;
END;
$$;

-- ======================================================= departamento (write)
--
-- Separada de `fn_update_company_user` porque o departamento é o único campo
-- do vínculo que não mexe em permissão: juntá-lo à função de papel faria uma
-- correção de departamento passar pela mesma porta que concede ADMIN.
CREATE OR REPLACE FUNCTION public.fn_set_company_user_department(
    p_company_id uuid,
    p_user_id    uuid,
    p_department text
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF NOT public.fn_is_admin(public.fn_current_user_id(), p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem alterar o departamento'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    UPDATE public.company_users
       SET department = NULLIF(btrim(p_department), ''),
           updated_on = now()
     WHERE company_id = p_company_id
       AND user_account_id = p_user_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuário não encontrado nesta empresa'
            USING ERRCODE = 'no_data_found';
    END IF;
END;
$$;

-- ============================================================= privilégios
--
-- `fn_list_company_users` perdeu os grants no DROP acima;
-- `fn_set_company_user_department` é nova. As duas valem para as mesmas roles
-- da allowlist de 01_security.sql e da migration de identidade por JWT.
DO $$
DECLARE
  v_sig regprocedure;
BEGIN
  FOR v_sig IN SELECT p.oid::regprocedure FROM pg_proc p
                WHERE p.pronamespace = 'public'::regnamespace
                  AND p.proname IN ('fn_list_company_users',
                                    'fn_set_company_user_department')
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon', v_sig);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO app_backend, authenticated', v_sig);
  END LOOP;
END $$;
