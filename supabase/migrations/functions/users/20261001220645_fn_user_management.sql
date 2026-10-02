
CREATE OR REPLACE FUNCTION public.fn_create_company_user(
    p_company_id uuid,
    p_login      text,
    p_pass_hash  text,
    p_role       public.user_role
) RETURNS uuid
LANGUAGE plpgsql AS $$
DECLARE
    v_actor    uuid := public.fn_current_user_id();
    v_login_id uuid;
BEGIN
    IF v_actor IS NULL OR NOT public.fn_is_admin(v_actor, p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem cadastrar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF public.fn_login_is_from_another_account(p_login, p_company_id) THEN
        RAISE EXCEPTION 'Login "%" já pertence a outra conta', p_login
            USING ERRCODE = 'unique_violation';
    END IF;

    INSERT INTO public.user_accounts (name, pass_hash)
    VALUES (p_login, p_pass_hash)
    ON CONFLICT (name) DO NOTHING
    RETURNING id INTO v_login_id;

    IF v_login_id IS NULL THEN
        SELECT id INTO v_login_id FROM public.user_accounts WHERE name = p_login;
    END IF;

    INSERT INTO public.company_users (company_id, user_account_id, role)
    VALUES (p_company_id, v_login_id, p_role);

    RETURN v_login_id;
END;
$$;



CREATE OR REPLACE FUNCTION public.fn_update_company_user(
    p_user_id    uuid,
    p_company_id uuid,
    p_new_login  text             DEFAULT NULL,
    p_new_role   public.user_role DEFAULT NULL,
    p_active     boolean          DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
BEGIN
    IF v_actor IS NULL OR NOT public.fn_is_admin(v_actor, p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem editar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- p_ignore_user_id = p_user_id  → ignora o próprio registro
    IF p_new_login IS NOT NULL
       AND public.fn_login_is_from_another_account(p_new_login, p_company_id, p_user_id)
    THEN
        RAISE EXCEPTION 'Login "%" já pertence a outra conta', p_new_login
            USING ERRCODE = 'unique_violation';
    END IF;

    IF p_new_login IS NOT NULL THEN
        UPDATE public.user_accounts
           SET name = p_new_login
         WHERE id = p_user_id;
    END IF;

    UPDATE public.company_users
       SET role       = COALESCE(p_new_role, role),
           active     = COALESCE(p_active,   active),
           updated_on = now()
     WHERE company_id         = p_company_id
       AND user_account_id = p_user_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuário % não pertence à empresa %', p_user_id, p_company_id;
    END IF;
END;
$$;



CREATE OR REPLACE FUNCTION public.fn_toggle_company_user(
    p_user_id    uuid,
    p_company_id uuid,
    p_active     boolean
) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
BEGIN
    IF v_actor IS NULL OR NOT public.fn_is_admin(v_actor, p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem ativar/desativar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    UPDATE public.company_users
       SET active     = p_active,
           updated_on = now()
     WHERE company_id         = p_company_id
       AND user_account_id = p_user_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuário % não pertence à empresa %', p_user_id, p_company_id;
    END IF;
END;
$$;


