-- Consistência US22/US20/estoque. Depende da sequência US20 e da correção
-- 20261031125500_us17_us20_product_lock_order.sql. Não faz backfill nem altera
-- saldos, vendas ou devoluções existentes. Efeito somente nas próximas chamadas.
-- Não acrescenta enums nem altera assinatura/retorno das RPCs.
-- Para rollback preferir correção incremental: não remover guardas sob tráfego.
BEGIN;

--  Configura o teto global da empresa
CREATE OR REPLACE FUNCTION public.fn_set_company_max_stock_limit(
    p_company_id uuid,
    p_limit integer
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    -- Validação: O limite não pode ser negativo
    IF p_limit IS NULL OR p_limit < 0 THEN
    RAISE EXCEPTION 'O limite máximo de estoque deve ser um número maior ou igual a zero'
        USING ERRCODE = 'check_violation';
    END IF;

    -- Validação de Permissão
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Apenas administradores podem alterar o teto global'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- Serializa configurações da empresa sem bloquear os KEY SHARE das FKs.
    PERFORM c.id FROM public.company c WHERE c.id = p_company_id FOR NO KEY UPDATE;
    -- Mantém estáveis os saldos dos produtos existentes durante a validação.
    PERFORM p.id FROM public.products p WHERE p.company_id = p_company_id
     ORDER BY p.barcode, p.id FOR UPDATE;

    IF EXISTS (
    SELECT 1 FROM public.product_stock ps
    JOIN public.products p ON p.id = ps.product_id
    WHERE p.company_id = p_company_id AND ps.max_quantity > p_limit
) THEN
    RAISE EXCEPTION 'Não é possível definir o teto para %, pois existem produtos com estoque máximo superior', p_limit
        USING ERRCODE = 'check_violation';
END IF;

    IF EXISTS (
        SELECT 1 FROM public.products p
         WHERE p.company_id = p_company_id AND p.stock > p_limit
    ) THEN
        RAISE EXCEPTION 'Não é possível definir o teto para %, pois existem produtos com saldo atual superior', p_limit
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.company SET max_stock_limit = p_limit WHERE id = p_company_id;
END;
$$;

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
    v_item_discount_total numeric;
    v_additional_discount numeric;
BEGIN
    v_original_total := NEW.total + NEW.discount;
    SELECT COALESCE(sum(si.discount_amount), 0) INTO v_item_discount_total
      FROM public.sale_items si
     WHERE si.sale_id = NEW.id AND si.company_id = NEW.company_id;
    v_additional_discount := NEW.discount - v_item_discount_total;
    IF v_additional_discount < 0 THEN
        RAISE EXCEPTION 'Desconto total menor que os descontos dos itens da venda'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.discount > 0 THEN
        NEW.discount_applied_by := COALESCE(
            NEW.discount_applied_by, NEW.created_by
        );
        -- Completar somente metadado FIXED legado. Desconto exclusivo dos
        -- itens e PERCENTAGE zero explícito devem continuar com parcela zero.
        IF NEW.sale_discount_type = 'FIXED' AND NEW.sale_discount_value = 0
           AND v_additional_discount > 0 THEN
            NEW.sale_discount_value := v_additional_discount;
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

REVOKE ALL ON FUNCTION public.fn_set_company_max_stock_limit(uuid, integer),
                       public.fn_validate_sale_discount_limit()
    FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_set_company_max_stock_limit(uuid, integer)
    TO authenticated, app_backend;
-- A função de trigger permanece fora da superfície RPC; não precisa de grant
-- aos papéis da aplicação para ser executada pelo gatilho existente.
NOTIFY pgrst, 'reload schema';
COMMIT;
