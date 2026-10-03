-- Escrita de produto no catálogo (US01). Fonte declarativa:
-- database/code/procedures/05_catalog.sql.

-- Edição de produto. Até aqui o catálogo só sabia criar e desativar: a tela de
-- "Editar produto" não tinha caminho de gravação no banco.
--
-- Não recebe p_company_id de propósito. A empresa é resolvida a partir da
-- própria linha de products; se viesse do chamador, bastaria informar uma
-- empresa onde ele tem papel ADMIN/STOCK para editar produto de outra.
--
-- Os parâmetros de dados são opcionais com DEFAULT NULL e a semântica é
-- "NULL = não alterar", resolvida com COALESCE contra o valor atual. Isso
-- deixa a tela mandar só o que o usuário mexeu; limpar um campo opcional não
-- é feito por aqui.
--
-- Não mexe em updated_on: products não tem essa coluna (triggers/01_updated_on
-- só cobre user_accounts, company_users e product_stock), e product_stock é
-- criado pelo trigger de INSERT, não por UPDATE.
CREATE OR REPLACE FUNCTION public.fn_update_products (
  p_product_id    UUID,
  p_barcode       TEXT              DEFAULT NULL,
  p_name          TEXT              DEFAULT NULL,
  p_sell_price    NUMERIC (10, 2)   DEFAULT NULL,
  p_buy_price     NUMERIC (10, 2)   DEFAULT NULL,
  p_unit          public.unit_enum  DEFAULT NULL,
  p_stock         INTEGER           DEFAULT NULL,
  p_item_category TEXT              DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
  v_company     UUID;
  v_category_id UUID;
BEGIN
  SELECT company_id INTO v_company
    FROM public.products
   WHERE id = p_product_id;

  -- Mesma estratégia de fn_set_product_active: mensagem única para produto
  -- inexistente e para falta de permissão, para não vazar a existência de
  -- produtos de outra empresa. A checagem vem antes de qualquer gravação:
  -- chamada negada não altera dado nenhum.
  IF v_company IS NULL
     OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
    RAISE EXCEPTION 'Produto não encontrado ou sem permissão'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  -- Categoria escopada pela empresa do produto, igual a fn_create_products: a
  -- FK composta (company_id, item_category) recusaria categoria de outra
  -- empresa de qualquer forma, mas aqui o erro sai nomeado.
  IF p_item_category IS NOT NULL THEN
    SELECT id INTO v_category_id
      FROM public.categories
     WHERE company_id = v_company AND name = p_item_category;

    IF v_category_id IS NULL THEN
      RAISE EXCEPTION 'Item category doesnt exist' USING ERRCODE = 'foreign_key_violation';
    END IF;
  END IF;

  UPDATE public.products
     SET barcode       = COALESCE(p_barcode, barcode),
         name          = COALESCE(p_name, name),
         buy_price     = COALESCE(p_buy_price, buy_price),
         sell_price    = COALESCE(p_sell_price, sell_price),
         unit          = COALESCE(p_unit, unit),
         stock         = COALESCE(p_stock, stock),
         item_category = COALESCE(v_category_id, item_category)
   WHERE id = p_product_id;
END;
$$;

-- GRANT próprio, de propósito. policies/01_security.sql faz revoke-all e
-- depois reconcede só o que está no array v_names, mas aquela migration
-- (20261003120100_policies_security.sql) já foi aplicada e não se reescreve
-- migration aplicada. Sem o GRANT aqui, fn_update_products nasceria sem
-- EXECUTE para app_backend e a tela de edição tomaria permission denied em
-- runtime. O nome também entrou no v_names da fonte declarativa, para que um
-- banco criado do zero continue coerente.
GRANT EXECUTE ON FUNCTION public.fn_update_products(
  UUID, TEXT, TEXT, NUMERIC, NUMERIC, public.unit_enum, INTEGER, TEXT
) TO app_backend;
