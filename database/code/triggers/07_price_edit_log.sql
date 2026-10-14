CREATE OR REPLACE FUNCTION public.trg_log_price_edit()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF OLD.sell_price IS DISTINCT FROM NEW.sell_price THEN
        INSERT INTO public.price_edit_log (
            updated_by, company_id, old_price, new_price, product_id
        ) VALUES (
            public.fn_current_user_id(), NEW.company_id,
            OLD.sell_price, NEW.sell_price, NEW.id
        );
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_price_edit_log ON public.products;
CREATE TRIGGER trg_price_edit_log
    AFTER UPDATE OF sell_price ON public.products
    FOR EACH ROW EXECUTE FUNCTION public.trg_log_price_edit();
