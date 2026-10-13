-- Cadastro/edição do vínculo. Identidade e senha permanecem no Supabase Auth.
CREATE OR REPLACE FUNCTION public.fn_save_company_member(
    p_company_id uuid, p_user_id uuid, p_email text,
    p_name text, p_role public.user_role, p_department text DEFAULT ''
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid := p_user_id;
    v_auth uuid;
    v_email text := lower(btrim(p_email));
BEGIN
    IF NOT public.fn_is_admin(public.fn_current_user_id(), p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem gerenciar usuários' USING ERRCODE = 'insufficient_privilege';
    END IF;
    PERFORM 1 FROM public.company WHERE id = p_company_id FOR UPDATE;
    IF NULLIF(btrim(p_name), '') IS NULL OR p_role IS NULL THEN
        RAISE EXCEPTION 'Nome e perfil são obrigatórios' USING ERRCODE = 'check_violation';
    END IF;
    IF v_id IS NULL THEN
        SELECT id INTO v_auth FROM auth.users WHERE lower(email) = v_email;
        IF v_auth IS NULL THEN
            RAISE EXCEPTION 'Conta Auth ainda não cadastrada' USING ERRCODE = 'no_data_found';
        END IF;
        SELECT id INTO v_id FROM public.user_accounts WHERE auth_user_id = v_auth;
        IF v_id IS NULL THEN
            -- Sentinel não autentica: o aplicativo usa exclusivamente Supabase Auth.
            INSERT INTO public.user_accounts(name, pass_hash, auth_user_id)
            VALUES (v_email, '$auth$' || gen_random_uuid()::text, v_auth)
            RETURNING id INTO v_id;
        END IF;
        IF EXISTS (SELECT 1 FROM public.company_users WHERE company_id = p_company_id AND user_account_id = v_id) THEN
            RAISE EXCEPTION 'Usuário já cadastrado nesta empresa' USING ERRCODE = 'unique_violation';
        END IF;
        INSERT INTO public.company_users(company_id, user_account_id, role, display_name, department)
        VALUES (p_company_id, v_id, p_role, btrim(p_name), NULLIF(btrim(p_department), ''));
    ELSE
        IF NOT EXISTS (SELECT 1 FROM public.company_users WHERE company_id = p_company_id AND user_account_id = v_id) THEN
            RAISE EXCEPTION 'Usuário não encontrado nesta empresa' USING ERRCODE = 'insufficient_privilege';
        END IF;
        IF p_role <> 'ADMIN' AND EXISTS (
            SELECT 1 FROM public.company_users WHERE company_id = p_company_id AND user_account_id = v_id AND role = 'ADMIN' AND active
        ) AND NOT EXISTS (
            SELECT 1 FROM public.company_users WHERE company_id = p_company_id AND user_account_id <> v_id AND role = 'ADMIN' AND active
        ) THEN
            RAISE EXCEPTION 'A empresa precisa manter um administrador ativo' USING ERRCODE = 'check_violation';
        END IF;
        UPDATE public.company_users SET role = p_role, display_name = btrim(p_name),
            department = NULLIF(btrim(p_department), '')
        WHERE company_id = p_company_id AND user_account_id = v_id;
    END IF;
    RETURN v_id;
END;
$$;
