-- Soft-delete de produto. Portado da branch companies_user_stock_configure
-- (database/archive/functions/product/create_product.sql). A policy de SELECT
-- em products não filtra por active: desativar esconde o produto da UI, não
-- do banco, e o histórico de caixa continua resolvendo a FK.
CREATE OR REPLACE FUNCTION public.fn_set_product_active (
  p_product_id UUID,
  p_active     BOOLEAN
)
RETURNS VOID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
  v_company UUID;
BEGIN
  SELECT company_id INTO v_company
    FROM public.products
   WHERE id = p_product_id;

  -- Mensagem única para produto inexistente e para falta de permissão: não
  -- vaza a existência de produtos de outra empresa.
  IF v_company IS NULL
     OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
    RAISE EXCEPTION 'Produto não encontrado ou sem permissão'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  IF p_active IS NULL THEN
    RAISE EXCEPTION 'p_active é obrigatório' USING ERRCODE = 'not_null_violation';
  END IF;

  UPDATE public.products SET active = p_active WHERE id = p_product_id;
END;
$$;
