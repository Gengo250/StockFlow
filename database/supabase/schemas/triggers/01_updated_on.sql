CREATE OR REPLACE FUNCTION public.trg_set_updated_on()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_on := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_user_accounts_updated BEFORE UPDATE ON public.user_accounts
    FOR EACH ROW EXECUTE FUNCTION public.trg_set_updated_on();
CREATE TRIGGER trg_company_users_updated BEFORE UPDATE ON public.company_users
    FOR EACH ROW EXECUTE FUNCTION public.trg_set_updated_on();
CREATE TRIGGER trg_product_stock_updated BEFORE UPDATE ON public.product_stock
    FOR EACH ROW EXECUTE FUNCTION public.trg_set_updated_on();
