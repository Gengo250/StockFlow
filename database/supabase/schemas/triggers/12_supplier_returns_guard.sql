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
