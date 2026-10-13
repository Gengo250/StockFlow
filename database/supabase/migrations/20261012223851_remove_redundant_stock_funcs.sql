DROP TRIGGER IF EXISTS trg_save_log_stock ON public.products;

DROP FUNCTION IF EXISTS public.trg_log_stock_change();
DROP FUNCTION IF EXISTS public.trg_create_log_stock_edit();

DROP TABLE IF EXISTS public.stock_log CASCADE;
