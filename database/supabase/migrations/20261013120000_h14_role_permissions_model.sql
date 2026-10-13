-- H14: modelo de perfis e permissões — auditoria de atribuição de perfil e
-- autoria nas escritas de negócio.
--
-- Incremental e não destrutiva: só CREATE e ADD COLUMN. As colunas de autoria
-- nascem nullable porque as linhas que já existem no banco foram criadas antes
-- de haver registro de autor, e inventar um autor para elas seria pior do que
-- admitir que não se sabe.

-- ------------------------------------------------- auditoria de permissões

CREATE TABLE public.role_change_log (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    actor_id       uuid,
    target_user_id uuid NOT NULL,
    role_before    public.user_role,
    role_after     public.user_role NOT NULL,
    active_before  boolean,
    active_after   boolean NOT NULL,
    changed_on     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_role_change_log_company
    ON public.role_change_log (company_id, changed_on DESC);
CREATE INDEX idx_role_change_log_target
    ON public.role_change_log (target_user_id);

-- Trigger, e não chamada dentro de cada função: hoje são cinco caminhos que
-- escrevem em company_users (fn_save_company_member, fn_update_company_user,
-- fn_toggle_company_user, fn_create_company_user e fn_register_company), e o
-- próximo nasceria sem auditoria se a regra morasse em cada um.
CREATE OR REPLACE FUNCTION public.trg_company_users_log_role()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND NEW.role = OLD.role
       AND NEW.active IS NOT DISTINCT FROM OLD.active THEN
        RETURN NEW;
    END IF;

    INSERT INTO public.role_change_log (
        company_id, actor_id, target_user_id,
        role_before, role_after, active_before, active_after
    ) VALUES (
        NEW.company_id,
        public.fn_current_user_id(),
        NEW.user_account_id,
        CASE WHEN TG_OP = 'UPDATE' THEN OLD.role END,
        NEW.role,
        CASE WHEN TG_OP = 'UPDATE' THEN OLD.active END,
        NEW.active
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_company_users_log_role ON public.company_users;
CREATE TRIGGER trg_company_users_log_role
    AFTER INSERT OR UPDATE ON public.company_users
    FOR EACH ROW EXECUTE FUNCTION public.trg_company_users_log_role();

-- --------------------------------------------- autoria nas escritas de negócio

ALTER TABLE public.products   ADD COLUMN IF NOT EXISTS created_by uuid;
ALTER TABLE public.categories ADD COLUMN IF NOT EXISTS created_by uuid;
ALTER TABLE public.clients    ADD COLUMN IF NOT EXISTS created_by uuid;
ALTER TABLE public.suppliers  ADD COLUMN IF NOT EXISTS created_by uuid;

-- As funções de criação passam a gravar fn_current_user_id(), no mesmo padrão
-- que fn_register_movement e fn_register_sale já usavam.

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

  IF EXISTS (
    SELECT 1 FROM public.categories
     WHERE company_id = p_company_id AND name = p_name
  ) THEN
    RAISE EXCEPTION 'Category already exists' USING ERRCODE = 'unique_violation';
  END IF;

  INSERT INTO public.categories (
    company_id,
    name,
    created_by
  )
  VALUES (
    p_company_id,
    p_name,
    public.fn_current_user_id()
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

  INSERT INTO public.products (
    company_id, barcode, name, buy_price, sell_price, unit, stock, item_category,
    created_by
  )
  VALUES (
    p_company_id, p_barcode, p_name, p_buy_price, p_sell_price, p_unit, 0, v_category_id,
    public.fn_current_user_id()
  )
  RETURNING id into v_new_id;

  IF COALESCE(p_stock, 0) > 0 THEN
    PERFORM public.fn_register_movement(
      p_company_id, v_new_id, 'ENTRADA', p_stock, 'Saldo inicial do cadastro', true);
  END IF;

  RETURN v_new_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_client(
    p_company_id uuid,
    p_name text,
    p_document text DEFAULT NULL,
    p_email text DEFAULT '',
    p_phone text DEFAULT '',
    p_notes text DEFAULT ''
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
    v_document text := NULLIF(regexp_replace(COALESCE(p_document, ''), '\D', '', 'g'), '');
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para cadastrar clientes nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_name IS NULL OR btrim(p_name) = '' THEN
        RAISE EXCEPTION 'Nome do cliente é obrigatório'
            USING ERRCODE = 'not_null_violation';
    END IF;
    IF NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL
       AND p_document !~ '^[0-9./[:space:]-]+$' THEN
        RAISE EXCEPTION 'CPF/CNPJ do cliente é inválido'
            USING ERRCODE = 'check_violation';
    END IF;
    IF (NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL AND v_document IS NULL)
       OR (v_document IS NOT NULL AND NOT public.fn_valid_br_document(v_document)) THEN
        RAISE EXCEPTION 'CPF/CNPJ do cliente é inválido'
            USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.clients (company_id, name, document, email, phone, notes,
                                created_by)
    VALUES (p_company_id, btrim(p_name), v_document,
            btrim(COALESCE(p_email, '')), btrim(COALESCE(p_phone, '')),
            btrim(COALESCE(p_notes, '')), public.fn_current_user_id())
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_supplier(
    p_company_id uuid,
    p_name text,
    p_document text DEFAULT NULL,
    p_phone text DEFAULT '',
    p_email text DEFAULT '',
    p_address text DEFAULT ''
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
    v_document text := NULLIF(regexp_replace(COALESCE(p_document, ''), '\D', '', 'g'), '');
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para cadastrar fornecedores nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_name IS NULL OR btrim(p_name) = '' THEN
        RAISE EXCEPTION 'Nome ou razão social do fornecedor é obrigatório'
            USING ERRCODE = 'not_null_violation';
    END IF;
    IF NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL
       AND p_document !~ '^[0-9./[:space:]-]+$' THEN
        RAISE EXCEPTION 'CPF/CNPJ do fornecedor é inválido'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NULLIF(btrim(COALESCE(p_document, '')), '') IS NOT NULL
       AND (v_document IS NULL OR NOT public.fn_valid_br_document(v_document)) THEN
        RAISE EXCEPTION 'CPF/CNPJ do fornecedor é inválido'
            USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.suppliers (company_id, name, document, phone, email, address,
                                  created_by)
    VALUES (p_company_id, btrim(p_name), v_document,
            btrim(COALESCE(p_phone, '')), btrim(COALESCE(p_email, '')),
            btrim(COALESCE(p_address, '')), public.fn_current_user_id())
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

-- ------------------------------------------------------- segurança do log

ALTER TABLE public.role_change_log ENABLE ROW LEVEL SECURITY;

-- SELECT, e só: o log é escrito exclusivamente pelo trigger SECURITY DEFINER.
-- Dar escrita aqui permitiria ao sistema auditado reescrever a auditoria.
GRANT SELECT ON public.role_change_log TO app_backend, authenticated;

DROP POLICY IF EXISTS role_change_log_select ON public.role_change_log;
CREATE POLICY role_change_log_select ON public.role_change_log
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[]));

-- A varredura de REVOKE de policies/01_security.sql não cobre função criada
-- por migration posterior — foi esse o buraco de fn_update_products, que
-- nasceu com EXECUTE para PUBLIC. As funções redefinidas acima já existiam e
-- mantêm seus grants, mas a de trigger é nova e não deve ser chamável por
-- ninguém de fora: trigger é invocado pelo Postgres, não pela aplicação.
REVOKE ALL ON FUNCTION public.trg_company_users_log_role()
  FROM PUBLIC, anon, authenticated, app_backend;
