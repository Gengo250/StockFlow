
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
