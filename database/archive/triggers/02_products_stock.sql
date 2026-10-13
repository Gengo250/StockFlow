-- Todo produto novo ganha uma linha em product_stock.
CREATE OR REPLACE FUNCTION public.trg_products_create_stock()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    INSERT INTO public.product_stock (product_id) VALUES (NEW.id) ON CONFLICT DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_products_create_stock AFTER INSERT ON public.products
    FOR EACH ROW EXECUTE FUNCTION public.trg_products_create_stock();
