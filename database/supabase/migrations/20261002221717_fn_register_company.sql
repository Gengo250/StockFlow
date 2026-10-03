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
