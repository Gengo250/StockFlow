
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


CREATE OR REPLACE FUNCTION public.trg_company_users_keep_admin()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF OLD.role = 'ADMIN' AND OLD.active
       AND (TG_OP = 'DELETE' OR NEW.role <> 'ADMIN' OR NOT NEW.active)
       AND EXISTS (SELECT 1 FROM public.company WHERE id = OLD.company_id)   -- ignora DELETE em cascata da empresa
       AND NOT EXISTS (SELECT 1 FROM public.company_users cd
                        WHERE cd.company_id = OLD.company_id AND cd.id <> OLD.id
                          AND cd.role = 'ADMIN' AND cd.active)
    THEN
        RAISE EXCEPTION 'A empresa precisa manter ao menos um administrador ativo'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER trg_company_users_keep_admin BEFORE UPDATE OR DELETE ON public.company_users
    FOR EACH ROW EXECUTE FUNCTION public.trg_company_users_keep_admin();
