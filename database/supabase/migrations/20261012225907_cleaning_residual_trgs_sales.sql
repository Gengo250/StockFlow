DROP TRIGGER IF EXISTS trg_save_log_sales ON public.sales;
DROP TRIGGER IF EXISTS trg_sale_successful ON public.sales;
DROP FUNCTION IF EXISTS public.trg_sale_successful() CASCADE;
DROP TABLE IF EXISTS public.sales_log CASCADE;
