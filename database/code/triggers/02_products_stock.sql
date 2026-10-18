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



CREATE OR REPLACE FUNCTION public.trg_check_product_max_stock()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company_id uuid;
    v_company_limit integer;
BEGIN
    -- Se max_quantity não foi informado, nada a validar
    IF NEW.max_quantity IS NULL THEN
        RETURN NEW;
    END IF;

    -- 1. Busca a empresa do produto e o teto da empresa
    SELECT p.company_id, c.max_stock_limit 
      INTO v_company_id, v_company_limit
      FROM public.products p
      JOIN public.company c ON c.id = p.company_id
     WHERE p.id = NEW.product_id;

    -- 2. Valida contra o teto da empresa
    IF v_company_limit IS NOT NULL AND NEW.max_quantity > v_company_limit THEN
        RAISE EXCEPTION 'O estoque máximo (%) excede o teto global configurado para a empresa (%)',
            NEW.max_quantity, v_company_limit
            USING ERRCODE = 'check_violation';
    END IF;

    -- 3. Garante que max_quantity >= min_quantity
    IF NEW.min_quantity IS NOT NULL AND NEW.max_quantity < NEW.min_quantity THEN
        RAISE EXCEPTION 'O estoque máximo (%) não pode ser inferior ao estoque mínimo (%)',
            NEW.max_quantity, NEW.min_quantity
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_check_product_max_stock ON public.product_stock;
CREATE TRIGGER trg_check_product_max_stock
    BEFORE INSERT OR UPDATE OF max_quantity, min_quantity
    ON public.product_stock
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_check_product_max_stock();