
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
