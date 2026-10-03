-- Gestão de contas e empresas. Depende de 01_identity e 02_authz.

CREATE OR REPLACE FUNCTION public.fn_get_login_credentials(p_login text)
RETURNS TABLE (account_id uuid, login text, pass_hash text, has_active_access boolean)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS $$
    SELECT ua.id, ua.name, ua.pass_hash,
           EXISTS (SELECT 1 FROM public.company_users cd
                     JOIN public.company c ON c.id = cd.company_id
                    WHERE cd.user_account_id = ua.id AND cd.active AND c.active)
      FROM public.user_accounts ua
     WHERE ua.name = lower(btrim(COALESCE(p_login, '')));
$$;

CREATE OR REPLACE FUNCTION public.fn_list_company_users(p_company_id uuid)
RETURNS TABLE (user_id uuid, login text, user_role public.user_role, is_active boolean, created_on timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF NOT public.fn_is_admin(public.fn_current_user_id(), p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem listar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN QUERY
    SELECT ua.id, ua.name, cd.role, cd.active, cd.created_on
      FROM public.company_users cd
      JOIN public.user_accounts ua ON ua.id = cd.user_account_id
     WHERE cd.company_id = p_company_id
     ORDER BY ua.name;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_company_user(
    p_company_id uuid,
    p_login      text,
    p_pass_hash  text,
    p_role       public.user_role
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_actor  uuid := public.fn_current_user_id();
    v_login  text := lower(btrim(COALESCE(p_login, '')));
    v_new_id uuid;
BEGIN
    IF v_actor IS NULL OR NOT public.fn_is_admin(v_actor, p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem cadastrar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF length(v_login) < 3 THEN
        RAISE EXCEPTION 'O login deve ter ao menos 3 caracteres' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT public.fn_is_valid_pass_hash(p_pass_hash) THEN
        RAISE EXCEPTION 'Hash de senha inválido (esperado "$algoritmo$...")' USING ERRCODE = 'check_violation';
    END IF;
    IF p_role IS NULL THEN
        RAISE EXCEPTION 'Perfil é obrigatório' USING ERRCODE = 'not_null_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM public.user_accounts WHERE name = v_login) THEN
        RAISE EXCEPTION 'Login "%" já está em uso', v_login USING ERRCODE = 'unique_violation';
    END IF;

    INSERT INTO public.user_accounts (name, pass_hash) VALUES (v_login, p_pass_hash)
    RETURNING id INTO v_new_id;

    INSERT INTO public.company_users (company_id, user_account_id, role)
    VALUES (p_company_id, v_new_id, p_role);

    RETURN v_new_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_update_company_user(
    p_user_id       uuid,
    p_company_id    uuid,
    p_new_login     text             DEFAULT NULL,
    p_new_role      public.user_role DEFAULT NULL,
    p_active        boolean          DEFAULT NULL,
    p_new_pass_hash text             DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
    v_login text := lower(btrim(p_new_login));
BEGIN
    IF v_actor IS NULL OR NOT public.fn_is_admin(v_actor, p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem editar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    PERFORM 1 FROM public.company_users
     WHERE company_id = p_company_id AND user_account_id = p_user_id
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuário % não pertence à empresa %', p_user_id, p_company_id;
    END IF;

    IF p_new_login IS NOT NULL OR p_new_pass_hash IS NOT NULL THEN
        -- login e senha são globais: só mexe se o usuário pertence APENAS a esta empresa
        IF EXISTS (SELECT 1 FROM public.company_users
                    WHERE user_account_id = p_user_id AND company_id <> p_company_id) THEN
            RAISE EXCEPTION 'Este usuário pertence a outras empresas; login/senha não podem ser alterados aqui'
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;

    IF p_new_login IS NOT NULL THEN
        IF length(v_login) < 3 THEN
            RAISE EXCEPTION 'O login deve ter ao menos 3 caracteres' USING ERRCODE = 'check_violation';
        END IF;
        IF EXISTS (SELECT 1 FROM public.user_accounts WHERE name = v_login AND id <> p_user_id) THEN
            RAISE EXCEPTION 'Login "%" já está em uso', v_login USING ERRCODE = 'unique_violation';
        END IF;
        UPDATE public.user_accounts SET name = v_login WHERE id = p_user_id;
    END IF;

    IF p_new_pass_hash IS NOT NULL THEN
        IF NOT public.fn_is_valid_pass_hash(p_new_pass_hash) THEN
            RAISE EXCEPTION 'Hash de senha inválido (esperado "$algoritmo$...")' USING ERRCODE = 'check_violation';
        END IF;
        UPDATE public.user_accounts SET pass_hash = p_new_pass_hash WHERE id = p_user_id;
    END IF;

    UPDATE public.company_users
       SET role   = COALESCE(p_new_role, role),
           active = COALESCE(p_active,   active)
     WHERE company_id = p_company_id AND user_account_id = p_user_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_toggle_company_user(
    p_user_id    uuid,
    p_company_id uuid,
    p_active     boolean
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
BEGIN
    IF v_actor IS NULL OR NOT public.fn_is_admin(v_actor, p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem ativar/desativar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    UPDATE public.company_users
       SET active = p_active
     WHERE company_id = p_company_id AND user_account_id = p_user_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuário % não pertence à empresa %', p_user_id, p_company_id;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_set_own_pass_hash(p_new_hash text)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
BEGIN
    IF v_actor IS NULL THEN
        RAISE EXCEPTION 'Usuário não identificado' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT public.fn_is_valid_pass_hash(p_new_hash) THEN
        RAISE EXCEPTION 'Hash de senha inválido (esperado "...")' USING ERRCODE = 'check_violation';
    END IF;
    UPDATE public.user_accounts SET pass_hash = p_new_hash WHERE id = v_actor;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_register_company(
    p_company_name text,
    p_cnpj         text,
    p_admin_login  text,
    p_admin_hash   text
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_user    uuid;
    v_login   text := lower(btrim(COALESCE(p_admin_login, '')));
BEGIN
    IF length(v_login) < 3 THEN
        RAISE EXCEPTION 'O login deve ter ao menos 3 caracteres' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT public.fn_is_valid_pass_hash(p_admin_hash) THEN
        RAISE EXCEPTION 'Hash de senha inválido (esperado "$algoritmo$...")' USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM public.user_accounts WHERE name = v_login) THEN
        RAISE EXCEPTION 'Login "%" já está em uso', v_login USING ERRCODE = 'unique_violation';
    END IF;

    INSERT INTO public.company (name, cnpj) VALUES (btrim(p_company_name), NULLIF(btrim(p_cnpj), ''))
    RETURNING id INTO v_company;
    INSERT INTO public.user_accounts (name, pass_hash) VALUES (v_login, p_admin_hash) RETURNING id INTO v_user;
    INSERT INTO public.company_users (company_id, user_account_id, role) VALUES (v_company, v_user, 'ADMIN');

    RETURN v_company;
END;
$$;
