
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
