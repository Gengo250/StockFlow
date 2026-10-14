CREATE OR REPLACE FUNCTION public.trg_log_stock_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO public.stock_log (
    user_id,
    barcode,
    quantity_changed,
    old_stock,
    new_stock
  ) VALUES (
    NEW.last_updated_by,
    NEW.barcode,
    (NEW.stock - OLD.stock),   
    OLD.stock,
    NEW.stock
  );
  
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_save_log_stock ON public.products;
CREATE TRIGGER trg_save_log_stock
AFTER UPDATE OF stock ON public.products
FOR EACH ROW
WHEN (OLD.stock IS DISTINCT FROM NEW.stock)
EXECUTE FUNCTION public.trg_log_stock_change();
