-- Cadastro de categorias e produtos. Depende de 02_authz.

CREATE OR REPLACE FUNCTION public.fn_create_categories (
  p_company_id UUID,
  p_name       TEXT
)
RETURNS UUID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
  v_new_id UUID;
BEGIN
  IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
    RAISE EXCEPTION 'Sem permissão para cadastrar categorias nesta empresa'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  -- categories é UNIQUE (company_id, name): o mesmo nome pode existir em
  -- outra empresa, então a checagem precisa ser escopada.
  IF EXISTS (
    SELECT 1 FROM public.categories
     WHERE company_id = p_company_id AND name = p_name
  ) THEN
    RAISE EXCEPTION 'Category already exists' USING ERRCODE = 'unique_violation';
  END IF;

  INSERT INTO public.categories (
    company_id,
    name
  )
  VALUES (
    p_company_id,
    p_name
  )
  RETURNING id INTO v_new_id;

  RETURN v_new_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_products (
  p_company_id    UUID,
  p_barcode       TEXT,
  p_name          TEXT,
  p_sell_price    NUMERIC (10, 2),
  p_buy_price     NUMERIC (10, 2)   DEFAULT NULL,
  p_unit          public.unit_enum  DEFAULT 'UN',
  p_stock         INTEGER           DEFAULT 0,
  p_item_category TEXT              DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
  v_new_id      UUID;
  v_category_id UUID;
BEGIN
  IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
    RAISE EXCEPTION 'Sem permissão para cadastrar produtos nesta empresa'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  IF p_item_category IS NOT NULL THEN
    SELECT id INTO v_category_id
      FROM public.categories
     WHERE company_id = p_company_id AND name = p_item_category;

    IF v_category_id IS NULL THEN
      RAISE EXCEPTION 'Item category doesnt exist' USING ERRCODE = 'foreign_key_violation';
    END IF;
  END IF;

  -- Nasce com saldo zero; o saldo informado vira a primeira movimentação.
  INSERT INTO public.products (
    company_id, barcode, name, buy_price, sell_price, unit, stock, item_category
  )
  VALUES (
    p_company_id, p_barcode, p_name, p_buy_price, p_sell_price, p_unit, 0, v_category_id
  )
  RETURNING id into v_new_id;

  IF COALESCE(p_stock, 0) > 0 THEN
    PERFORM public.fn_register_movement(
      p_company_id, v_new_id, 'ENTRADA', p_stock, 'Saldo inicial do cadastro', true);
  END IF;

  RETURN v_new_id;
END;
$$;

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
  v_atual       INTEGER;
  v_delta       INTEGER;
BEGIN
  SELECT company_id, stock INTO v_company, v_atual
    FROM public.products
   WHERE id = p_product_id;

  IF v_company IS NULL
     OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
    RAISE EXCEPTION 'Produto não encontrado ou sem permissão'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  IF p_item_category IS NOT NULL THEN
    SELECT id INTO v_category_id
      FROM public.categories
     WHERE company_id = v_company AND name = p_item_category;

    IF v_category_id IS NULL THEN
      RAISE EXCEPTION 'Item category doesnt exist' USING ERRCODE = 'foreign_key_violation';
    END IF;
  END IF;

  -- `stock` SAI do UPDATE: quem muda saldo é movimentação.
  UPDATE public.products
     SET barcode       = COALESCE(p_barcode, barcode),
         name          = COALESCE(p_name, name),
         buy_price     = COALESCE(p_buy_price, buy_price),
         sell_price    = COALESCE(p_sell_price, sell_price),
         unit          = COALESCE(p_unit, unit),
         item_category = COALESCE(v_category_id, item_category)
   WHERE id = p_product_id;

  -- Saldo informado vira a movimentação que falta para chegar nele. O
  -- formulário manda a tela inteira, então "igual ao atual" é o caso comum e
  -- não pode gerar movimentação de quantidade zero.
  IF p_stock IS NOT NULL THEN
    v_delta := p_stock - v_atual;
    IF v_delta > 0 THEN
      PERFORM public.fn_register_movement(
        v_company, p_product_id, 'ENTRADA', v_delta, 'Ajuste pelo cadastro', true);
    ELSIF v_delta < 0 THEN
      PERFORM public.fn_register_movement(
        v_company, p_product_id, 'SAIDA', -v_delta, 'Ajuste pelo cadastro', true);
    END IF;
  END IF;
END;
$$;

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
