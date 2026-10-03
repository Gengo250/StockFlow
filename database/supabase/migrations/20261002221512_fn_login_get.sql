CREATE OR REPLACE FUNCTION public.fn_get_login_credentials(p_login text)
RETURNS TABLE (account_id uuid, login text, pass_hash text, has_active_access boolean)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS $$
    SELECT ua.id, ua.name, ua.pass_hash,
           EXISTS (SELECT 1 FROM public.company_users cd
                     JOIN public.company c ON c.id = cd.company_id
                    WHERE cd.user_account_id = ua.id AND cd.active AND c.active)
      FROM public.user_accounts ua
     WHERE ua.name = lower(btrim(COALESCE(p_login, '')));
$$;


CREATE OR REPLACE FUNCTION public.fn_my_companies()
RETURNS TABLE (company_id uuid, company_name text, user_role public.user_role)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS $$
    SELECT c.id, c.name, cd.role
      FROM public.company_users cd
      JOIN public.company c ON c.id = cd.company_id
     WHERE cd.user_account_id = public.fn_current_user_id()
       AND cd.active AND c.active
     ORDER BY c.name;
$$;