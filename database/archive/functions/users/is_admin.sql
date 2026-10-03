CREATE OR REPLACE FUNCTION public.fn_is_admin(
    p_user_id    uuid,
    p_company_id uuid
) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS $$
    SELECT EXISTS (
        SELECT 1
          FROM public.company_users cd
          JOIN public.company c ON c.id = cd.company_id
         WHERE cd.user_account_id = p_user_id
           AND cd.company_id      = p_company_id
           AND cd.role            = 'ADMIN'
           AND cd.active AND c.active
    );
$$;
