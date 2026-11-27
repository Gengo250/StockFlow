-- US30: devolver produtos ao fornecedor usando SAIDA e vínculos próprios.
-- US30: devoluções ao fornecedor, identificadas por vínculo e não por novo enum.
ALTER TABLE public.products ADD CONSTRAINT uq_products_company_id_supplier_returns UNIQUE (company_id,id);

CREATE TABLE public.supplier_returns (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE RESTRICT,
    supplier_id uuid NOT NULL,
    purchase_id uuid,
    created_by uuid NOT NULL,
    created_on timestamptz NOT NULL DEFAULT now(),
    idempotency_key uuid NOT NULL,
    request_payload jsonb NOT NULL,
    UNIQUE(company_id,id),
    UNIQUE(company_id,id,supplier_id),
    UNIQUE(company_id,idempotency_key),
    FOREIGN KEY(company_id,supplier_id) REFERENCES public.suppliers(company_id,id) ON DELETE RESTRICT,
    FOREIGN KEY(company_id,purchase_id,supplier_id) REFERENCES public.purchases(company_id,id,supplier_id) ON DELETE RESTRICT
);
CREATE INDEX idx_supplier_returns_history ON public.supplier_returns(company_id,created_on DESC,id);
CREATE INDEX idx_supplier_returns_purchase ON public.supplier_returns(company_id,purchase_id) WHERE purchase_id IS NOT NULL;

CREATE TABLE public.supplier_return_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL,
    supplier_return_id uuid NOT NULL,
    position integer NOT NULL CHECK(position>0),
    product_id uuid NOT NULL,
    quantity integer NOT NULL CHECK(quantity>0 AND quantity<=1000000),
    reason text NOT NULL CHECK(length(reason)<=1000 AND reason !~ '^[[:space:]]*$'),
    UNIQUE(company_id,supplier_return_id,id),
    UNIQUE(supplier_return_id,position),
    FOREIGN KEY(company_id,supplier_return_id) REFERENCES public.supplier_returns(company_id,id) ON DELETE RESTRICT,
    FOREIGN KEY(company_id,product_id) REFERENCES public.products(company_id,id) ON DELETE RESTRICT
);
CREATE INDEX idx_supplier_return_items_header ON public.supplier_return_items(company_id,supplier_return_id);

ALTER TABLE public.stock_movements ADD COLUMN supplier_return_id uuid;
ALTER TABLE public.stock_movements ADD COLUMN supplier_return_item_id uuid;
ALTER TABLE public.stock_movements ADD CONSTRAINT fk_movement_supplier_return_item
    FOREIGN KEY(company_id,supplier_return_id,supplier_return_item_id)
    REFERENCES public.supplier_return_items(company_id,supplier_return_id,id) ON DELETE RESTRICT;
ALTER TABLE public.stock_movements ADD CONSTRAINT fk_movement_supplier_return_supplier
    FOREIGN KEY(company_id,supplier_return_id,supplier_id)
    REFERENCES public.supplier_returns(company_id,id,supplier_id) ON DELETE RESTRICT;
ALTER TABLE public.stock_movements ADD CONSTRAINT ck_movement_supplier_return
    CHECK((supplier_return_id IS NULL AND supplier_return_item_id IS NULL) OR
          (supplier_return_id IS NOT NULL AND supplier_return_item_id IS NOT NULL
           AND supplier_id IS NOT NULL AND kind='SAIDA' AND status='CONFIRMADA'
           AND confirmed_on IS NOT NULL AND sale_id IS NULL AND sale_item_id IS NULL
           AND return_id IS NULL AND cancellation_id IS NULL
           AND adjustment_reason IS NULL AND counted_balance IS NULL));
CREATE UNIQUE INDEX uq_movement_supplier_return_item ON public.stock_movements(supplier_return_item_id)
    WHERE supplier_return_item_id IS NOT NULL;
CREATE INDEX idx_movements_supplier_return ON public.stock_movements(company_id,supplier_return_id)
    WHERE supplier_return_id IS NOT NULL;

-- A view interna nunca é concedida diretamente à aplicação.
CREATE OR REPLACE FUNCTION public.fn_supplier_return_view(p_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
 SELECT jsonb_build_object('id',r.id,'company_id',r.company_id,'supplier_id',r.supplier_id,
   'supplier_name',s.name,'purchase_id',r.purchase_id,'created_by',r.created_by,
   'created_by_name',COALESCE(NULLIF(btrim(cu.display_name),''),ua.name),
   'created_on',r.created_on,'idempotency_key',r.idempotency_key,
   'items',COALESCE((SELECT jsonb_agg(jsonb_build_object(
       'id',i.id,'product_id',i.product_id,'product_code',p.barcode,'product_name',p.name,
       'quantity',i.quantity,'reason',i.reason,'movement_id',m.id
     ) ORDER BY i.position)
     FROM public.supplier_return_items i JOIN public.products p ON p.id=i.product_id
     JOIN public.stock_movements m ON m.supplier_return_item_id=i.id
     WHERE i.supplier_return_id=r.id),'[]'::jsonb))
 FROM public.supplier_returns r JOIN public.suppliers s ON s.id=r.supplier_id
 LEFT JOIN public.user_accounts ua ON ua.id=r.created_by
 LEFT JOIN public.company_users cu ON cu.company_id=r.company_id AND cu.user_account_id=r.created_by
 WHERE r.id=p_id;
$$;

CREATE OR REPLACE FUNCTION public.fn_register_supplier_return(
 p_company_id uuid,p_supplier_id uuid,p_items jsonb,p_purchase_id uuid DEFAULT NULL,
 p_idempotency_key uuid DEFAULT gen_random_uuid()
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE
 v_actor uuid:=public.fn_current_user_id(); v_id uuid; v_item_id uuid; v_product_id uuid;
 v_request jsonb; v_existing public.supplier_returns%ROWTYPE; v_item record;
 v_before jsonb; v_after jsonb; v_result jsonb; v_when timestamptz:=now();
BEGIN
 IF v_actor IS NULL OR NOT public.fn_has_role(p_company_id,ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
   RAISE EXCEPTION 'Sem permissão para devolver ao fornecedor nesta empresa' USING ERRCODE='42501';
 END IF;
 IF p_idempotency_key IS NULL THEN
   RAISE EXCEPTION 'Chave da requisição obrigatória' USING ERRCODE='23514';
 END IF;
 IF p_items IS NULL OR jsonb_typeof(p_items)<>'array' THEN
   RAISE EXCEPTION 'Informe uma lista de itens da devolução' USING ERRCODE='23514';
 END IF;
 IF jsonb_array_length(p_items) NOT BETWEEN 1 AND 100 THEN
   RAISE EXCEPTION 'Informe de 1 a 100 itens da devolução' USING ERRCODE='23514';
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_items) x WHERE
   jsonb_typeof(x)<>'object' OR COALESCE(jsonb_typeof(x->'product_code'),'null')<>'string'
   OR btrim(COALESCE(x->>'product_code',''))='' OR COALESCE(jsonb_typeof(x->'quantity'),'null')<>'number'
   OR COALESCE(x->>'quantity','') !~ '^[1-9][0-9]*$'
   OR COALESCE(jsonb_typeof(x->'reason'),'null')<>'string'
   OR COALESCE(x->>'reason','') ~ '^[[:space:]]*$' OR length(x->>'reason')>1000) THEN
   RAISE EXCEPTION 'Cada item exige produto, quantidade inteira positiva e motivo de até 1000 caracteres' USING ERRCODE='23514';
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_items) x WHERE (x->>'quantity')::numeric>1000000) THEN
   RAISE EXCEPTION 'Quantidade por item não pode exceder 1000000' USING ERRCODE='23514';
 END IF;
 SELECT jsonb_build_object('supplier_id',p_supplier_id,'purchase_id',p_purchase_id,'items',jsonb_agg(
   jsonb_build_object('product_code',btrim(x.val->>'product_code'),'quantity',(x.val->>'quantity')::integer,
     'reason',btrim(x.val->>'reason',E' \t\r\n')) ORDER BY x.ord)) INTO v_request
 FROM jsonb_array_elements(p_items) WITH ORDINALITY x(val,ord);
 -- Serializa a mesma requisição antes de conferir saldo: reenvio não baixa duas vezes.
 PERFORM pg_advisory_xact_lock(hashtextextended(p_company_id::text||':'||p_idempotency_key::text,0));
 SELECT * INTO v_existing FROM public.supplier_returns
 WHERE company_id=p_company_id AND idempotency_key=p_idempotency_key FOR UPDATE;
 IF FOUND THEN
   IF v_existing.created_by<>v_actor OR v_existing.request_payload<>v_request THEN
     RAISE EXCEPTION 'Chave de devolução já usada por outra requisição' USING ERRCODE='23514';
   END IF;
   RETURN public.fn_supplier_return_view(v_existing.id);
 END IF;
 IF p_purchase_id IS NOT NULL THEN
   PERFORM 1 FROM public.purchases WHERE id=p_purchase_id AND company_id=p_company_id
     AND supplier_id=p_supplier_id AND status='RECEBIDA' FOR SHARE;
   IF NOT FOUND THEN
     RAISE EXCEPTION 'Compra de origem deve estar recebida e pertencer ao fornecedor e à empresa' USING ERRCODE='23514';
   END IF;
 END IF;
 -- Inativação impede novas compras; não impede devolver um recebimento anterior.
 PERFORM 1 FROM public.suppliers WHERE id=p_supplier_id AND company_id=p_company_id FOR SHARE;
 IF NOT FOUND THEN
   RAISE EXCEPTION 'Fornecedor não encontrado nesta empresa' USING ERRCODE='23503';
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(v_request->'items') x
   WHERE NOT EXISTS(SELECT 1 FROM public.products p WHERE p.company_id=p_company_id AND p.barcode=x->>'product_code')) THEN
   RAISE EXCEPTION 'Produto da devolução não encontrado nesta empresa' USING ERRCODE='23503';
 END IF;
 IF p_purchase_id IS NOT NULL AND EXISTS(SELECT 1 FROM jsonb_array_elements(v_request->'items') x
   WHERE NOT EXISTS(SELECT 1 FROM public.purchase_items i JOIN public.products p ON p.id=i.product_id
     WHERE i.purchase_id=p_purchase_id AND i.company_id=p_company_id AND p.barcode=x->>'product_code')) THEN
   RAISE EXCEPTION 'Produto não pertence à compra de origem' USING ERRCODE='23514';
 END IF;
 -- Mesma ordem por código usada nas vendas. Todos os produtos são travados antes da primeira saída.
 PERFORM p.id FROM public.products p WHERE p.company_id=p_company_id
   AND p.barcode IN(SELECT x->>'product_code' FROM jsonb_array_elements(v_request->'items') x)
 ORDER BY p.barcode,p.id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM public.products p JOIN(
   SELECT x->>'product_code' AS code,sum((x->>'quantity')::bigint) AS qty
   FROM jsonb_array_elements(v_request->'items') x GROUP BY x->>'product_code'
 ) q ON q.code=p.barcode WHERE p.company_id=p_company_id AND q.qty>p.stock) THEN
   RAISE EXCEPTION 'Saldo disponível insuficiente para a devolução ao fornecedor' USING ERRCODE='23514';
 END IF;
 SELECT jsonb_object_agg(p.barcode,p.stock) INTO v_before FROM public.products p
 WHERE p.company_id=p_company_id AND p.barcode IN(SELECT x->>'product_code' FROM jsonb_array_elements(v_request->'items') x);
 INSERT INTO public.supplier_returns(company_id,supplier_id,purchase_id,created_by,created_on,idempotency_key,request_payload)
 VALUES(p_company_id,p_supplier_id,p_purchase_id,v_actor,v_when,p_idempotency_key,v_request) RETURNING id INTO v_id;
 FOR v_item IN SELECT x.val,x.ord FROM jsonb_array_elements(v_request->'items') WITH ORDINALITY x(val,ord) LOOP
   SELECT id INTO v_product_id FROM public.products WHERE company_id=p_company_id AND barcode=v_item.val->>'product_code';
   INSERT INTO public.supplier_return_items(company_id,supplier_return_id,position,product_id,quantity,reason)
   VALUES(p_company_id,v_id,v_item.ord,v_product_id,(v_item.val->>'quantity')::integer,v_item.val->>'reason') RETURNING id INTO v_item_id;
   INSERT INTO public.stock_movements(company_id,product_id,kind,quantity,status,note,created_by,created_on,confirmed_on,
     supplier_id,purchase_id,supplier_return_id,supplier_return_item_id)
   VALUES(p_company_id,v_product_id,'SAIDA',(v_item.val->>'quantity')::integer,'CONFIRMADA',
     'DEVOLUCAO_FORNECEDOR - '||v_id::text||' - '||(v_item.val->>'reason'),v_actor,v_when,v_when,
     p_supplier_id,p_purchase_id,v_id,v_item_id);
 END LOOP;
 SELECT jsonb_object_agg(p.barcode,p.stock) INTO v_after FROM public.products p
 WHERE p.company_id=p_company_id AND p.barcode IN(SELECT x->>'product_code' FROM jsonb_array_elements(v_request->'items') x);
 v_result:=public.fn_supplier_return_view(v_id);
 INSERT INTO public.audit_log(company_id,user_id,action,entity,entity_id,old_values,new_values,is_critical)
 VALUES(p_company_id,v_actor::text,'DEVOLUCAO_FORNECEDOR','supplier_returns',v_id::text,
   jsonb_build_object('stock',v_before),jsonb_build_object('return',v_result,'stock',v_after),true);
 RETURN v_result;
END $$;

CREATE OR REPLACE FUNCTION public.fn_get_supplier_return(p_company_id uuid,p_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
 IF NOT public.fn_has_role(p_company_id,ARRAY['ADMIN','STOCK']::public.user_role[])
   OR NOT EXISTS(SELECT 1 FROM public.supplier_returns WHERE company_id=p_company_id AND id=p_id) THEN
   RAISE EXCEPTION 'Devolução não encontrada ou sem permissão' USING ERRCODE='42501';
 END IF;
 RETURN public.fn_supplier_return_view(p_id);
END $$;

CREATE OR REPLACE FUNCTION public.fn_list_supplier_returns(p_company_id uuid,p_supplier_id uuid DEFAULT NULL,
 p_purchase_id uuid DEFAULT NULL,p_limit integer DEFAULT 50,p_offset integer DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE result jsonb;
BEGIN
 IF NOT public.fn_has_role(p_company_id,ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
   RAISE EXCEPTION 'Sem permissão para consultar devoluções ao fornecedor' USING ERRCODE='42501';
 END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 OR p_offset IS NULL OR p_offset<0 THEN
   RAISE EXCEPTION 'Paginação inválida' USING ERRCODE='23514';
 END IF;
 SELECT COALESCE(jsonb_agg(public.fn_supplier_return_view(r.id) ORDER BY r.created_on DESC,r.id DESC),'[]'::jsonb)
 INTO result FROM(SELECT id,created_on FROM public.supplier_returns WHERE company_id=p_company_id
   AND (p_supplier_id IS NULL OR supplier_id=p_supplier_id) AND (p_purchase_id IS NULL OR purchase_id=p_purchase_id)
   ORDER BY created_on DESC,id DESC LIMIT p_limit OFFSET p_offset) r;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public.trg_supplier_return_immutable()
RETURNS trigger LANGUAGE plpgsql SET search_path=public,pg_temp AS $$
BEGIN
 RAISE EXCEPTION 'Devoluções ao fornecedor são imutáveis; histórico não pode ser editado ou excluído' USING ERRCODE='23514';
END $$;
CREATE TRIGGER trg_supplier_returns_immutable BEFORE UPDATE OR DELETE ON public.supplier_returns
 FOR EACH ROW EXECUTE FUNCTION public.trg_supplier_return_immutable();
CREATE TRIGGER trg_supplier_return_items_immutable BEFORE UPDATE OR DELETE ON public.supplier_return_items
 FOR EACH ROW EXECUTE FUNCTION public.trg_supplier_return_immutable();

CREATE OR REPLACE FUNCTION public.trg_guard_supplier_return_movement()
RETURNS trigger LANGUAGE plpgsql SET search_path=public,pg_temp AS $$
BEGIN
 IF TG_OP<>'INSERT' AND OLD.supplier_return_id IS NOT NULL THEN
   RAISE EXCEPTION 'Movimentação de devolução ao fornecedor não pode ser alterada ou cancelada isoladamente' USING ERRCODE='23514';
 END IF;
 IF TG_OP<>'DELETE' AND NEW.supplier_return_id IS NOT NULL AND NOT EXISTS(
   SELECT 1 FROM public.supplier_return_items i JOIN public.supplier_returns r ON r.id=i.supplier_return_id
   WHERE i.id=NEW.supplier_return_item_id AND i.supplier_return_id=NEW.supplier_return_id
     AND i.company_id=NEW.company_id AND i.product_id=NEW.product_id AND i.quantity=NEW.quantity
     AND r.supplier_id=NEW.supplier_id AND r.purchase_id IS NOT DISTINCT FROM NEW.purchase_id
     AND r.created_by=NEW.created_by) THEN
   RAISE EXCEPTION 'Movimentação diverge do item da devolução ao fornecedor' USING ERRCODE='23514';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_guard_supplier_return_movement BEFORE INSERT OR UPDATE OR DELETE ON public.stock_movements
 FOR EACH ROW EXECUTE FUNCTION public.trg_guard_supplier_return_movement();

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
