CREATE OR REPLACE FUNCTION public.trg_sale_successful()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  item RECORD;
BEGIN
  INSERT INTO public.sales_log (
    sale_id,
    created_by 
  ) VALUES (
    NEW.id,
    NEW.created_by
  );

  FOR item IN
    SELECT
      product_id,
      quantity
    FROM public.sale_items
    WHERE sale_id = NEW.id
      AND product_id IS NOT NULL
  LOOP 
    
    UPDATE public.products
    SET
      stock = stock - item.quantity,
      last_updated_by = NEW.created_by
    WHERE id = item.product_id;
  END LOOP;
  
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_save_log_sales ON public.sales;
CREATE TRIGGER trg_save_log_sales
AFTER UPDATE OF status ON public.sales
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'COMPLETE')
EXECUTE FUNCTION public.trg_sale_successful();
