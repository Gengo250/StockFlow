ALTER TABLE public.supplier_returns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.supplier_return_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.supplier_returns,public.supplier_return_items FROM PUBLIC,anon,authenticated,app_backend;
GRANT SELECT ON public.supplier_returns,public.supplier_return_items TO authenticated,app_backend;
CREATE POLICY supplier_returns_select ON public.supplier_returns FOR SELECT TO authenticated,app_backend
 USING(public.fn_has_role(company_id,ARRAY['ADMIN','STOCK']::public.user_role[]));
CREATE POLICY supplier_return_items_select ON public.supplier_return_items FOR SELECT TO authenticated,app_backend
 USING(public.fn_has_role(company_id,ARRAY['ADMIN','STOCK']::public.user_role[]));
REVOKE ALL ON FUNCTION public.fn_supplier_return_view(uuid),public.trg_supplier_return_immutable(),
 public.trg_guard_supplier_return_movement() FROM PUBLIC,anon,authenticated,app_backend;
REVOKE ALL ON FUNCTION public.fn_register_supplier_return(uuid,uuid,jsonb,uuid,uuid),
 public.fn_get_supplier_return(uuid,uuid),public.fn_list_supplier_returns(uuid,uuid,uuid,integer,integer) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.fn_register_supplier_return(uuid,uuid,jsonb,uuid,uuid),
 public.fn_get_supplier_return(uuid,uuid),public.fn_list_supplier_returns(uuid,uuid,uuid,integer,integer) TO authenticated,app_backend;
