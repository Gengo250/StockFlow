
CREATE OR REPLACE FUNCTION public.fn_is_admin(
    p_user_id    uuid,
    p_company_id uuid
) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
          FROM public.company_users
         WHERE user_account_id = p_user_id
           AND company_id         = p_company_id
           AND role               = 'ADMIN'
           AND active             = true
    );
$$;

