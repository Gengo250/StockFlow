-- Toda conclusão de venda, inclusive caminhos legados, aplica o limite de desconto.
CREATE OR REPLACE FUNCTION public.fn_validate_sale_discount_limit()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_seller_role public.user_role;
    v_limit numeric;
    v_original_total numeric;
    v_percent numeric := 0;
BEGIN
    v_original_total := NEW.total + NEW.discount;
    IF NEW.discount > 0 THEN
        NEW.discount_applied_by := COALESCE(
            NEW.discount_applied_by, NEW.created_by
        );
        IF NEW.sale_discount_value = 0 THEN
            NEW.sale_discount_value := NEW.discount;
            NEW.sale_discount_type := 'FIXED';
        END IF;
    END IF;

    IF NEW.discount > 0 AND NEW.discount_applied_by IS NULL THEN
        RAISE EXCEPTION 'A autoria do desconto é obrigatória'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT cu.role INTO v_seller_role
      FROM public.company_users cu
     WHERE cu.company_id = NEW.company_id
       AND cu.user_account_id = NEW.created_by
       AND cu.active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Responsável pela venda não pertence à empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF v_seller_role = 'SELLER' THEN
        SELECT COALESCE((
            SELECT sdl.limit_percent
              FROM public.sale_discount_limits sdl
             WHERE sdl.company_id = NEW.company_id AND sdl.role = 'SELLER'
        ), 10.00) INTO v_limit;

        IF v_original_total > 0 THEN
            v_percent := NEW.discount * 100 / v_original_total;
        END IF;
        IF v_percent > v_limit
           AND (
               NEW.discount_authorized_by IS NULL
               OR NOT public.fn_is_admin(
                   NEW.discount_authorized_by, NEW.company_id
               )
           ) THEN
            RAISE EXCEPTION
                'Desconto acima do limite de %%%: aprovação de ADMIN necessária',
                v_limit
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sale_discount_guard ON public.sales;
CREATE TRIGGER trg_sale_discount_guard
    BEFORE UPDATE OF status ON public.sales
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'CONCLUIDA')
    EXECUTE FUNCTION public.fn_validate_sale_discount_limit();
