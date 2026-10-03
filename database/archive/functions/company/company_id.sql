CREATE OR REPLACE FUNCTION public.fn_my_company_ids()
RETURNS SETOF uuid
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS $$
    SELECT cd.company_id
      FROM public.company_users cd
      JOIN public.company c ON c.id = cd.company_id
     WHERE cd.user_account_id = public.fn_current_user_id()
       AND cd.active AND c.active;
$$;