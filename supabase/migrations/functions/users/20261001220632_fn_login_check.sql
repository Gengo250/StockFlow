
CREATE OR REPLACE FUNCTION public.fn_login_is_from_another_account(
    p_login          text,
    p_company_id     uuid,
    p_ignore_user_id uuid DEFAULT NULL
) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
          FROM public.user_accounts ar
          JOIN public.company_users cd ON cd.user_account_id = ar.id
         WHERE ar.name       = p_login
           AND cd.company_id <> p_company_id
           AND (p_ignore_user_id IS NULL OR ar.id <> p_ignore_user_id)
    );
$$;
