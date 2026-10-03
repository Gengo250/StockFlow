CREATE OR REPLACE FUNCTION public.fn_has_role(
    p_company_id uuid,
    p_roles      public.user_role[]
) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS $$
    SELECT EXISTS (
        SELECT 1
          FROM public.company_users cd
          JOIN public.company c ON c.id = cd.company_id
         WHERE cd.user_account_id = public.fn_current_user_id()
           AND cd.company_id      = p_company_id
           AND cd.role            = ANY (p_roles)
           AND cd.active AND c.active
    );
$$;


CREATE OR REPLACE FUNCTION public.fn_is_member(p_company_id uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS $$
    SELECT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK','SELLER']::public.user_role[]);
$$;

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

