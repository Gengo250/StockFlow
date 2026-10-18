CREATE TABLE IF NOT EXISTS public.price_edit_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    updated_by uuid,
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    last_updated_on timestamp with time zone NOT NULL DEFAULT now(),
    old_price numeric NOT NULL,
    new_price numeric NOT NULL,
    product_id uuid NOT NULL REFERENCES public.products(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_price_edit_log_product_id ON public.price_edit_log(product_id);
CREATE INDEX IF NOT EXISTS idx_price_edit_log_company_id ON public.price_edit_log(company_id);
CREATE OR REPLACE FUNCTION public.trg_log_price_edit()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF OLD.sell_price IS DISTINCT FROM NEW.sell_price THEN
        INSERT INTO public.price_edit_log (
            updated_by,
            company_id,
            last_updated_on,
            old_price,
            new_price,
            product_id
        ) VALUES (
            NEW.last_updated_by,
            NEW.company_id,
            now(),
            OLD.sell_price,
            NEW.sell_price,
            NEW.id
        );
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_price_edit_log ON public.products;
CREATE TRIGGER trg_price_edit_log
AFTER UPDATE OF sell_price ON public.products
FOR EACH ROW
EXECUTE FUNCTION public.trg_log_price_edit();
