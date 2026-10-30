-- US20: leitura por empresa; escrita direta bloqueada. Não expor RPCs incompletas.

ALTER TABLE public.returns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.return_items ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.returns, public.return_items
  FROM PUBLIC, anon, authenticated, app_backend;
GRANT SELECT ON public.returns, public.return_items TO app_backend, authenticated;

DROP POLICY IF EXISTS returns_select ON public.returns;
DROP POLICY IF EXISTS return_items_select ON public.return_items;

CREATE POLICY returns_select ON public.returns
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[]));

CREATE POLICY return_items_select ON public.return_items
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[]));
