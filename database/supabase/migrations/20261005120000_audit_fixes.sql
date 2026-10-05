-- Correções da auditoria: campos do formulário, gravação atômica, usuários e integridade.
-- Não reaplica carga histórica nem converte mínimos existentes.


ALTER TABLE public.products ADD COLUMN IF NOT EXISTS description    text NOT NULL DEFAULT '' CHECK (length(description) <= 2000);

ALTER TABLE public.products ADD COLUMN IF NOT EXISTS ncm            text NOT NULL DEFAULT '' CHECK (ncm = '' OR ncm ~ '^[0-9]{8}$');

ALTER TABLE public.products ADD COLUMN IF NOT EXISTS ean            text NOT NULL DEFAULT '' CHECK (ean = '' OR ean ~ '^([0-9]{8}|[0-9]{12,14})$');

ALTER TABLE public.products ADD COLUMN IF NOT EXISTS location       text NOT NULL DEFAULT '' CHECK (length(location) <= 200);

ALTER TABLE public.products ADD COLUMN IF NOT EXISTS low_stock_alert boolean NOT NULL DEFAULT true;

ALTER TABLE public.products ADD COLUMN IF NOT EXISTS image_data     text NOT NULL DEFAULT '' CHECK (length(image_data) <= 350000);

ALTER TABLE public.company_users ADD COLUMN IF NOT EXISTS display_name text;

-- Gestão de contas e empresas. Depende de 01_identity e 02_authz.

CREATE OR REPLACE FUNCTION public.fn_get_login_credentials(p_login text)
RETURNS TABLE (account_id uuid, login text, pass_hash text, has_active_access boolean)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS $$
    SELECT ua.id, ua.name, ua.pass_hash,
           EXISTS (SELECT 1 FROM public.company_users cd
                     JOIN public.company c ON c.id = cd.company_id
                    WHERE cd.user_account_id = ua.id AND cd.active AND c.active)
      FROM public.user_accounts ua
     WHERE ua.name = lower(btrim(COALESCE(p_login, '')));
$$;

-- Diretório da tela de Usuários: nome, login, departamento, perfil, status e
-- último acesso.
--
-- O último acesso é DERIVADO de `auth.users.last_sign_in_at`, sem coluna
-- própria. O Supabase Auth já registra isso a cada login e ninguém precisa
-- mantê-lo sincronizado; uma coluna nossa exigiria gravar a cada entrada,
-- erraria para quem tem acesso a duas empresas e ficaria velha em todo login
-- que não passasse por esta aplicação.
--
-- Ler `auth.users` é possível porque a função é SECURITY DEFINER e o dono
-- alcança aquele schema. A junção pela esquerda com o Auth é obrigatória:
-- conta ainda não vinculada precisa continuar aparecendo, sem e-mail e sem
-- último acesso — é exatamente o usuário sobre o qual o administrador
-- precisa agir.
CREATE OR REPLACE FUNCTION public.fn_list_company_users(p_company_id uuid)
RETURNS TABLE (
    user_id      uuid,
    login        text,
    display_name text,
    department   text,
    user_role    public.user_role,
    is_active    boolean,
    last_access  timestamptz,
    created_on   timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF NOT public.fn_is_admin(public.fn_current_user_id(), p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem listar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN QUERY
    SELECT
        ua.id,
        -- `::text` obrigatório: `auth.users.email` é `character varying(255)`
        -- e `COALESCE(varchar, text)` NÃO resolve para `text` sozinho. A
        -- troca de tipo candidato em `select_common_type` só acontece quando
        -- a conversão implícita vale num sentido só, e entre `varchar` e
        -- `text` ela vale nos dois — o candidato fica no primeiro argumento,
        -- `varchar`, e o `RETURN QUERY` morre em "structure of query does not
        -- match function result type". Só na execução: o corpo de plpgsql não
        -- é validado na criação.
        COALESCE(au.email, ua.name)::text,
        -- Redundante hoje (`->>` já devolve text), mantido porque a expressão
        -- depende de `auth.users`, schema gerido pelo Supabase: o contrato
        -- desta coluna não deve mudar junto com a plataforma.
        COALESCE(
            NULLIF(btrim(cd.display_name), ''),
            NULLIF(btrim(au.raw_user_meta_data->>'name'), ''),
            NULLIF(btrim(au.raw_user_meta_data->>'full_name'), ''),
            ua.name
        )::text,
        cd.department,
        cd.role,
        cd.active,
        au.last_sign_in_at,
        cd.created_on
      FROM public.company_users cd
      JOIN public.user_accounts ua ON ua.id = cd.user_account_id
      LEFT JOIN auth.users au ON au.id = ua.auth_user_id
     WHERE cd.company_id = p_company_id
     ORDER BY 3;
END;
$$;

-- Departamento tem função própria, separada de `fn_update_company_user`: é o
-- único campo do vínculo que não mexe em permissão, e juntá-lo à função de
-- papel faria uma correção de departamento passar pela mesma porta que
-- concede ADMIN.
CREATE OR REPLACE FUNCTION public.fn_set_company_user_department(
    p_company_id uuid,
    p_user_id    uuid,
    p_department text
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF NOT public.fn_is_admin(public.fn_current_user_id(), p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem alterar o departamento'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    UPDATE public.company_users
       SET department = NULLIF(btrim(p_department), ''),
           updated_on = now()
     WHERE company_id = p_company_id
       AND user_account_id = p_user_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuário não encontrado nesta empresa'
            USING ERRCODE = 'no_data_found';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_company_user(
    p_company_id uuid,
    p_login      text,
    p_pass_hash  text,
    p_role       public.user_role
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_actor  uuid := public.fn_current_user_id();
    v_login  text := lower(btrim(COALESCE(p_login, '')));
    v_new_id uuid;
BEGIN
    IF v_actor IS NULL OR NOT public.fn_is_admin(v_actor, p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem cadastrar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF length(v_login) < 3 THEN
        RAISE EXCEPTION 'O login deve ter ao menos 3 caracteres' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT public.fn_is_valid_pass_hash(p_pass_hash) THEN
        RAISE EXCEPTION 'Hash de senha inválido (esperado "$algoritmo$...")' USING ERRCODE = 'check_violation';
    END IF;
    IF p_role IS NULL THEN
        RAISE EXCEPTION 'Perfil é obrigatório' USING ERRCODE = 'not_null_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM public.user_accounts WHERE name = v_login) THEN
        RAISE EXCEPTION 'Login "%" já está em uso', v_login USING ERRCODE = 'unique_violation';
    END IF;

    INSERT INTO public.user_accounts (name, pass_hash) VALUES (v_login, p_pass_hash)
    RETURNING id INTO v_new_id;

    INSERT INTO public.company_users (company_id, user_account_id, role)
    VALUES (p_company_id, v_new_id, p_role);

    RETURN v_new_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_update_company_user(
    p_user_id       uuid,
    p_company_id    uuid,
    p_new_login     text             DEFAULT NULL,
    p_new_role      public.user_role DEFAULT NULL,
    p_active        boolean          DEFAULT NULL,
    p_new_pass_hash text             DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
    v_login text := lower(btrim(p_new_login));
BEGIN
    IF v_actor IS NULL OR NOT public.fn_is_admin(v_actor, p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem editar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    PERFORM 1 FROM public.company_users
     WHERE company_id = p_company_id AND user_account_id = p_user_id
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuário % não pertence à empresa %', p_user_id, p_company_id;
    END IF;

    IF p_new_login IS NOT NULL OR p_new_pass_hash IS NOT NULL THEN
        -- login e senha são globais: só mexe se o usuário pertence APENAS a esta empresa
        IF EXISTS (SELECT 1 FROM public.company_users
                    WHERE user_account_id = p_user_id AND company_id <> p_company_id) THEN
            RAISE EXCEPTION 'Este usuário pertence a outras empresas; login/senha não podem ser alterados aqui'
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;

    IF p_new_login IS NOT NULL THEN
        IF length(v_login) < 3 THEN
            RAISE EXCEPTION 'O login deve ter ao menos 3 caracteres' USING ERRCODE = 'check_violation';
        END IF;
        IF EXISTS (SELECT 1 FROM public.user_accounts WHERE name = v_login AND id <> p_user_id) THEN
            RAISE EXCEPTION 'Login "%" já está em uso', v_login USING ERRCODE = 'unique_violation';
        END IF;
        UPDATE public.user_accounts SET name = v_login WHERE id = p_user_id;
    END IF;

    IF p_new_pass_hash IS NOT NULL THEN
        IF NOT public.fn_is_valid_pass_hash(p_new_pass_hash) THEN
            RAISE EXCEPTION 'Hash de senha inválido (esperado "$algoritmo$...")' USING ERRCODE = 'check_violation';
        END IF;
        UPDATE public.user_accounts SET pass_hash = p_new_pass_hash WHERE id = p_user_id;
    END IF;

    UPDATE public.company_users
       SET role   = COALESCE(p_new_role, role),
           active = COALESCE(p_active,   active)
     WHERE company_id = p_company_id AND user_account_id = p_user_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_toggle_company_user(
    p_user_id    uuid,
    p_company_id uuid,
    p_active     boolean
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
BEGIN
    IF v_actor IS NULL OR NOT public.fn_is_admin(v_actor, p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem ativar/desativar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    UPDATE public.company_users
       SET active = p_active
     WHERE company_id = p_company_id AND user_account_id = p_user_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuário % não pertence à empresa %', p_user_id, p_company_id;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_set_own_pass_hash(p_new_hash text)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
BEGIN
    IF v_actor IS NULL THEN
        RAISE EXCEPTION 'Usuário não identificado' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT public.fn_is_valid_pass_hash(p_new_hash) THEN
        RAISE EXCEPTION 'Hash de senha inválido (esperado "...")' USING ERRCODE = 'check_violation';
    END IF;
    UPDATE public.user_accounts SET pass_hash = p_new_hash WHERE id = v_actor;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_register_company(
    p_company_name text,
    p_cnpj         text,
    p_admin_login  text,
    p_admin_hash   text
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_user    uuid;
    v_login   text := lower(btrim(COALESCE(p_admin_login, '')));
BEGIN
    IF length(v_login) < 3 THEN
        RAISE EXCEPTION 'O login deve ter ao menos 3 caracteres' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT public.fn_is_valid_pass_hash(p_admin_hash) THEN
        RAISE EXCEPTION 'Hash de senha inválido (esperado "$algoritmo$...")' USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM public.user_accounts WHERE name = v_login) THEN
        RAISE EXCEPTION 'Login "%" já está em uso', v_login USING ERRCODE = 'unique_violation';
    END IF;

    INSERT INTO public.company (name, cnpj) VALUES (btrim(p_company_name), NULLIF(btrim(p_cnpj), ''))
    RETURNING id INTO v_company;
    INSERT INTO public.user_accounts (name, pass_hash) VALUES (v_login, p_admin_hash) RETURNING id INTO v_user;
    INSERT INTO public.company_users (company_id, user_account_id, role) VALUES (v_company, v_user, 'ADMIN');

    RETURN v_company;
END;
$$;


-- Registro e confirmação de movimentações. Depende de stock_movements
-- (tables/05) e de fn_has_role (02_authz).
--
-- Vem depois de 04_stock e antes de 05_catalog porque `fn_create_products` e
-- `fn_update_products` passaram a registrar movimentação em vez de escrever
-- `products.stock`.

-- Saldo confirmado de um produto. Uma função, e não a expressão repetida no
-- trigger e na carga inicial: duas cópias da mesma soma divergem, e a
-- divergência aqui significa saldo errado na tela.
-- VOLATILE, e não STABLE: ela é chamada de dentro de um trigger AFTER, onde
-- precisa enxergar a linha que acabou de ser gravada. STABLE amarra a função
-- ao snapshot da consulta chamadora, e um saldo calculado sobre o estado
-- ANTERIOR ficaria errado por uma movimentação a cada vez — erro que só
-- apareceria em produção, somando silenciosamente. O custo é perder inlining
-- numa função que só o trigger e a conferência usam.
CREATE OR REPLACE FUNCTION public.fn_confirmed_balance(p_product_id uuid)
RETURNS integer
LANGUAGE sql VOLATILE
SET search_path = public AS $$
    SELECT COALESCE(SUM(
        CASE m.kind WHEN 'ENTRADA' THEN m.quantity ELSE -m.quantity END
    ), 0)::integer
      FROM public.stock_movements m
     WHERE m.product_id = p_product_id
       AND m.status = 'CONFIRMADA';
$$;

-- Registra uma movimentação. Nasce PENDENTE salvo pedido explícito.
CREATE OR REPLACE FUNCTION public.fn_register_movement(
    p_company_id uuid,
    p_product_id uuid,
    p_kind       public.movement_kind,
    p_quantity   integer,
    p_note       text    DEFAULT NULL,
    p_confirm    boolean DEFAULT false
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para movimentar estoque nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantidade deve ser maior que zero (recebida: %)', p_quantity
            USING ERRCODE = 'check_violation';
    END IF;

    -- O produto precisa ser DA empresa informada. Sem esta checagem, quem é
    -- STOCK numa empresa movimentaria o estoque de outra.
    PERFORM 1 FROM public.products
     WHERE id = p_product_id AND company_id = p_company_id AND active FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Produto não encontrado ou inativo nesta empresa'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO public.stock_movements
           (company_id, product_id, kind, quantity, status, note,
            created_by, confirmed_on)
    VALUES (p_company_id, p_product_id, p_kind, p_quantity,
            CASE WHEN p_confirm THEN 'CONFIRMADA' ELSE 'PENDENTE' END::public.movement_status,
            p_note, public.fn_current_user_id(),
            CASE WHEN p_confirm THEN now() END)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

-- Confirma uma movimentação pendente. É esta transição que muda o saldo.
CREATE OR REPLACE FUNCTION public.fn_confirm_movement(p_movement_id uuid)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_status  public.movement_status;
    v_product uuid;
BEGIN
    SELECT company_id, product_id INTO v_company, v_product
      FROM public.stock_movements WHERE id = p_movement_id;

    -- Mensagem única para inexistente e sem permissão: não vaza a existência
    -- de movimentações de outra empresa.
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Movimentação não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    PERFORM 1 FROM public.products WHERE id = v_product AND active FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Produto inativo não pode ser movimentado' USING ERRCODE = 'check_violation';
    END IF;
    SELECT status INTO v_status FROM public.stock_movements
     WHERE id = p_movement_id FOR UPDATE;
    IF v_status <> 'PENDENTE' THEN
        RAISE EXCEPTION 'Só movimentação pendente pode ser confirmada (situação atual: %)', v_status
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.stock_movements
       SET status = 'CONFIRMADA', confirmed_on = now()
     WHERE id = p_movement_id;
END;
$$;

-- Cancela. Cancelar uma CONFIRMADA desfaz o efeito dela no saldo, porque o
-- trigger recalcula a soma das que seguem confirmadas.
CREATE OR REPLACE FUNCTION public.fn_cancel_movement(p_movement_id uuid)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_product uuid;
BEGIN
    SELECT company_id, product_id INTO v_company, v_product
      FROM public.stock_movements WHERE id = p_movement_id;

    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Movimentação não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    PERFORM 1 FROM public.products WHERE id = v_product FOR UPDATE;
    UPDATE public.stock_movements
       SET status = 'CANCELADA'
     WHERE id = p_movement_id;
END;
$$;


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
   WHERE id = p_product_id FOR UPDATE;

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


-- Persistência de clientes e do fluxo de vendas atual.

CREATE OR REPLACE FUNCTION public.fn_list_company_clients(
    p_company_id uuid,
    p_search text DEFAULT NULL
) RETURNS TABLE (
    client_id uuid,
    name text,
    document text,
    email text,
    phone text,
    notes text,
    active boolean,
    created_on timestamptz,
    updated_on timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_search text := lower(btrim(COALESCE(p_search, '')));
    v_digits text := regexp_replace(COALESCE(p_search, ''), '\D', '', 'g');
BEGIN
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Sem permissão para consultar clientes nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN QUERY
    SELECT c.id, c.name, c.document, c.email, c.phone, c.notes,
           c.active, c.created_on, c.updated_on
      FROM public.clients c
     WHERE c.company_id = p_company_id
       AND (
           v_search = ''
           OR c.name ILIKE '%' || v_search || '%'
           OR lower(c.email) LIKE '%' || v_search || '%'
           OR (v_digits <> '' AND
               regexp_replace(c.phone, '\D', '', 'g') LIKE '%' || v_digits || '%')
           OR (v_digits <> '' AND
               COALESCE(c.document, '') LIKE '%' || v_digits || '%')
       )
     ORDER BY lower(c.name), c.id;
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

    INSERT INTO public.clients (company_id, name, document, email, phone, notes)
    VALUES (p_company_id, btrim(p_name), v_document,
            btrim(COALESCE(p_email, '')), btrim(COALESCE(p_phone, '')),
            btrim(COALESCE(p_notes, '')))
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_update_client(
    p_client_id uuid,
    p_name text,
    p_document text DEFAULT NULL,
    p_email text DEFAULT '',
    p_phone text DEFAULT '',
    p_notes text DEFAULT '',
    p_active boolean DEFAULT true
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company_id uuid;
    v_document text := NULLIF(regexp_replace(COALESCE(p_document, ''), '\D', '', 'g'), '');
BEGIN
    SELECT company_id INTO v_company_id
      FROM public.clients WHERE id = p_client_id;
    IF v_company_id IS NULL
       OR NOT public.fn_has_role(v_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Cliente não encontrado ou sem permissão'
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

    UPDATE public.clients
       SET name = btrim(p_name),
           document = v_document,
           email = btrim(COALESCE(p_email, '')),
           phone = btrim(COALESCE(p_phone, '')),
           notes = btrim(COALESCE(p_notes, '')),
           active = COALESCE(p_active, active)
     WHERE id = p_client_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_set_client_active(
    p_client_id uuid,
    p_active boolean
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company_id uuid;
BEGIN
    SELECT company_id INTO v_company_id
      FROM public.clients WHERE id = p_client_id;
    IF v_company_id IS NULL
       OR NOT public.fn_has_role(v_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Cliente não encontrado ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    UPDATE public.clients SET active = p_active WHERE id = p_client_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_register_sale(
    p_company_id uuid,
    p_client_id uuid,
    p_product_id uuid,
    p_total numeric
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
    v_client_name text;
    v_product_name text;
    v_product_code text;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para registrar vendas nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_total IS NULL OR p_total < 0 OR p_total::text IN ('NaN', 'Infinity', '-Infinity') THEN
        RAISE EXCEPTION 'Valor da venda inválido' USING ERRCODE = 'check_violation';
    END IF;

    SELECT name INTO v_client_name
      FROM public.clients
     WHERE id = p_client_id AND company_id = p_company_id AND active
     FOR SHARE;
    IF v_client_name IS NULL THEN
        RAISE EXCEPTION 'Cliente não encontrado, inativo ou sem permissão'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT name, barcode INTO v_product_name, v_product_code
      FROM public.products
     WHERE id = p_product_id AND company_id = p_company_id AND active
     FOR SHARE;
    IF v_product_name IS NULL THEN
        RAISE EXCEPTION 'Produto não encontrado, inativo ou sem permissão'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO public.sales (
        company_id, client_id, product_id, client_name,
        product_name, product_code, total, created_by
    ) VALUES (
        p_company_id, p_client_id, p_product_id, v_client_name,
        v_product_name, COALESCE(v_product_code, ''), p_total,
        public.fn_current_user_id()
    )
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;


-- Uma transação por formulário: nenhum produto parcialmente salvo.
CREATE OR REPLACE FUNCTION public.fn_save_product(
    p_company_id uuid, p_product_id uuid, p_data jsonb
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid := p_product_id;
    v_company uuid;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para salvar produtos' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_data IS NULL OR COALESCE(btrim(p_data->>'code'), '') = '' THEN
        RAISE EXCEPTION 'Identificador é obrigatório' USING ERRCODE = 'check_violation';
    END IF;
    IF (p_data->>'stock')::integer < 0 THEN
        RAISE EXCEPTION 'Estoque não pode ser negativo' USING ERRCODE = 'check_violation';
    END IF;
    IF v_id IS NULL THEN
        v_id := public.fn_create_products(
            p_company_id => p_company_id, p_barcode => p_data->>'code',
            p_name => p_data->>'name', p_sell_price => (p_data->>'sale_price')::numeric,
            p_buy_price => (p_data->>'cost')::numeric, p_unit => (p_data->>'unit')::public.unit_enum,
            p_stock => (p_data->>'stock')::integer, p_item_category => p_data->>'category');
    ELSE
        SELECT company_id INTO v_company FROM public.products
         WHERE id = v_id FOR UPDATE;
        IF v_company IS DISTINCT FROM p_company_id THEN
            RAISE EXCEPTION 'Produto não encontrado ou sem permissão' USING ERRCODE = 'insufficient_privilege';
        END IF;
        PERFORM public.fn_update_products(
            p_product_id => v_id, p_barcode => p_data->>'code', p_name => p_data->>'name',
            p_sell_price => (p_data->>'sale_price')::numeric, p_buy_price => (p_data->>'cost')::numeric,
            p_unit => (p_data->>'unit')::public.unit_enum, p_stock => (p_data->>'stock')::integer,
            p_item_category => p_data->>'category');
    END IF;
    PERFORM public.fn_set_product_supplier(v_id, (p_data->>'supplier_id')::uuid);
    PERFORM public.fn_set_min_stock(v_id, (p_data->>'minimum_stock')::integer);
    PERFORM public.fn_set_product_active(v_id, COALESCE((p_data->>'active')::boolean, true));
    UPDATE public.products SET
        description = COALESCE(p_data->>'description', ''), ncm = COALESCE(p_data->>'ncm', ''),
        ean = COALESCE(p_data->>'ean', ''), location = COALESCE(p_data->>'location', ''),
        low_stock_alert = COALESCE((p_data->>'low_stock_alert')::boolean, true),
        image_data = COALESCE(p_data->>'image_data', '')
    WHERE id = v_id;
    RETURN v_id;
END;
$$;


-- Cadastro/edição do vínculo. Identidade e senha permanecem no Supabase Auth.
CREATE OR REPLACE FUNCTION public.fn_save_company_member(
    p_company_id uuid, p_user_id uuid, p_email text,
    p_name text, p_role public.user_role, p_department text DEFAULT ''
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid := p_user_id;
    v_auth uuid;
    v_email text := lower(btrim(p_email));
BEGIN
    IF NOT public.fn_is_admin(public.fn_current_user_id(), p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem gerenciar usuários' USING ERRCODE = 'insufficient_privilege';
    END IF;
    PERFORM 1 FROM public.company WHERE id = p_company_id FOR UPDATE;
    IF NULLIF(btrim(p_name), '') IS NULL OR p_role IS NULL THEN
        RAISE EXCEPTION 'Nome e perfil são obrigatórios' USING ERRCODE = 'check_violation';
    END IF;
    IF v_id IS NULL THEN
        SELECT id INTO v_auth FROM auth.users WHERE lower(email) = v_email;
        IF v_auth IS NULL THEN
            RAISE EXCEPTION 'Conta Auth ainda não cadastrada' USING ERRCODE = 'no_data_found';
        END IF;
        SELECT id INTO v_id FROM public.user_accounts WHERE auth_user_id = v_auth;
        IF v_id IS NULL THEN
            -- Sentinel não autentica: o aplicativo usa exclusivamente Supabase Auth.
            INSERT INTO public.user_accounts(name, pass_hash, auth_user_id)
            VALUES (v_email, '$auth$' || gen_random_uuid()::text, v_auth)
            RETURNING id INTO v_id;
        END IF;
        IF EXISTS (SELECT 1 FROM public.company_users WHERE company_id = p_company_id AND user_account_id = v_id) THEN
            RAISE EXCEPTION 'Usuário já cadastrado nesta empresa' USING ERRCODE = 'unique_violation';
        END IF;
        INSERT INTO public.company_users(company_id, user_account_id, role, display_name, department)
        VALUES (p_company_id, v_id, p_role, btrim(p_name), NULLIF(btrim(p_department), ''));
    ELSE
        IF NOT EXISTS (SELECT 1 FROM public.company_users WHERE company_id = p_company_id AND user_account_id = v_id) THEN
            RAISE EXCEPTION 'Usuário não encontrado nesta empresa' USING ERRCODE = 'insufficient_privilege';
        END IF;
        IF p_role <> 'ADMIN' AND EXISTS (
            SELECT 1 FROM public.company_users WHERE company_id = p_company_id AND user_account_id = v_id AND role = 'ADMIN' AND active
        ) AND NOT EXISTS (
            SELECT 1 FROM public.company_users WHERE company_id = p_company_id AND user_account_id <> v_id AND role = 'ADMIN' AND active
        ) THEN
            RAISE EXCEPTION 'A empresa precisa manter um administrador ativo' USING ERRCODE = 'check_violation';
        END IF;
        UPDATE public.company_users SET role = p_role, display_name = btrim(p_name),
            department = NULLIF(btrim(p_department), '')
        WHERE company_id = p_company_id AND user_account_id = v_id;
    END IF;
    RETURN v_id;
END;
$$;


-- O gatilho de último administrador já existe desde
-- 20261002213525_trg_update_users.sql; aqui só o CORPO é trocado, para
-- ganhar o FOR UPDATE que serializa duas portas de administração
-- concorrentes. Criar um segundo gatilho para a mesma regra deixaria a
-- empresa com duas mensagens e dois SQLSTATE para a mesma recusa.
CREATE OR REPLACE FUNCTION public.trg_company_users_keep_admin()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF OLD.role = 'ADMIN' AND OLD.active
       AND (TG_OP = 'DELETE' OR NEW.role <> 'ADMIN' OR NOT NEW.active)
    THEN
        -- Trava a empresa antes de contar. FOUND falso significa empresa
        -- removida: é o DELETE em cascata, que não deve ser barrado.
        PERFORM 1 FROM public.company WHERE id = OLD.company_id FOR UPDATE;
        IF FOUND AND NOT EXISTS (
            SELECT 1 FROM public.company_users cd
             WHERE cd.company_id = OLD.company_id AND cd.id <> OLD.id
               AND cd.role = 'ADMIN' AND cd.active
        ) THEN
            RAISE EXCEPTION 'A empresa precisa manter ao menos um administrador ativo'
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;


-- Modelo de segurança: role de aplicação, RLS e grants.
-- Portado de database/archive/policies/setup_security.sql (branch
-- companies_user_stock_configure, PR #9), adaptado ao schema desta árvore.
--
-- Vem por último em schema_paths: depende das tabelas (01-04), das funções de
-- autorização (02_authz) e da view de estoque (views/01).

-- Role sem login: a aplicação se conecta como ela, nunca como owner.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
    CREATE ROLE app_backend NOLOGIN NOINHERIT;
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO app_backend;

-- ------------------------------------------------------------------ RLS

ALTER TABLE public.company        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_accounts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.company_users  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_stock  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stock_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clients        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.suppliers       ENABLE ROW LEVEL SECURITY;

-- register não tem coluna de empresa (tables/02_cash_register.sql: "Caixa.
-- Independente das demais tabelas."), então não há como escopar por tenant.
-- RLS fica habilitada sem policy — nega tudo por padrão para quem não é owner
-- — e nenhum GRANT SELECT é dado. Ver nota no fim do arquivo.
ALTER TABLE public.register       ENABLE ROW LEVEL SECURITY;

-- access_register fica DE FORA de propósito: pr_validate_login
-- (procedures/06_cash_register.sql) não é SECURITY DEFINER e lê essa tabela
-- como invoker. Habilitar RLS aqui faria todo login do caixa cair em
-- NO_DATA_FOUND e retornar is_valid = FALSE silenciosamente.

-- -------------------------------------------------------------- privilégios

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, anon, authenticated, app_backend;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL     ON TABLES    FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

-- Leitura direta só onde existe policy que escopa por empresa.
-- user_accounts e company_users ficam sem SELECT: o acesso a eles passa
-- obrigatoriamente pelas funções SECURITY DEFINER (fn_list_company_users etc).
--
-- `authenticated` entra junto com `app_backend` porque existem DOIS clientes
-- legítimos do mesmo recorte: um backend dono da conexão (identidade pelo GUC
-- `app.user_id`) e o app desktop falando REST (identidade pelo JWT). Quem
-- separa um do outro é `fn_current_user_id()`, não o privilégio.
GRANT SELECT ON public.company,
                public.categories,
                public.products,
                public.product_stock,
                public.stock_movements,
                public.clients,
                public.suppliers,
                public.sales,
                public.vw_stock_situation,
                public.vw_stock_alerts
  TO app_backend, authenticated;

-- ----------------------------------------------------------------- policies

DROP POLICY IF EXISTS company_select       ON public.company;
DROP POLICY IF EXISTS categories_select    ON public.categories;
DROP POLICY IF EXISTS products_select      ON public.products;
DROP POLICY IF EXISTS product_stock_select ON public.product_stock;
DROP POLICY IF EXISTS stock_movements_select ON public.stock_movements;
DROP POLICY IF EXISTS clients_select          ON public.clients;
DROP POLICY IF EXISTS sales_select            ON public.sales;
DROP POLICY IF EXISTS suppliers_select        ON public.suppliers;

-- Policy é por role: o GRANT acima deixa `authenticated` chegar à tabela, mas
-- sem aparecer no TO da policy ela veria zero linha. O predicado é o MESMO
-- para as duas roles de propósito — duas regras para o mesmo dado divergem.
CREATE POLICY company_select ON public.company FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(id));

CREATE POLICY categories_select ON public.categories FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

CREATE POLICY products_select ON public.products FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

-- product_stock não tem company_id; herda o escopo via products, que já tem
-- a sua própria policy aplicada nesta mesma subconsulta.
-- stock_movements tem company_id próprio (duplicado de products de
-- propósito): a policy escopa direto, sem entrar no catálogo a cada linha.
CREATE POLICY stock_movements_select ON public.stock_movements
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

CREATE POLICY clients_select ON public.clients
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

CREATE POLICY sales_select ON public.sales
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

CREATE POLICY suppliers_select ON public.suppliers
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_has_role(company_id, ARRAY['ADMIN','STOCK']::public.user_role[]));

CREATE POLICY product_stock_select ON public.product_stock
  FOR SELECT TO app_backend, authenticated
  USING (EXISTS (
    SELECT 1 FROM public.products p WHERE p.id = product_stock.product_id
  ));

-- ------------------------------------------------------ execute nas funções

-- Fecha tudo primeiro: função nova que alguém adicionar não nasce pública.
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT p.oid::regprocedure AS sig
             FROM pg_proc p
             JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.prokind = 'f'
  LOOP
    EXECUTE format(
      'REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated, app_backend', r.sig);
  END LOOP;
END $$;

-- Reabre só a superfície pública da aplicação. O RAISE no fim é proposital:
-- se uma função da lista sumir num refactor, a migration falha alto em vez de
-- deixar a aplicação sem permissão em runtime.
DO $$
DECLARE
  v_names text[] := ARRAY[
    'fn_get_login_credentials', 'fn_register_company', 'fn_set_own_pass_hash',
    'fn_create_company_user', 'fn_update_company_user', 'fn_toggle_company_user',
    'fn_list_company_users', 'fn_set_company_user_department',
    'fn_create_categories', 'fn_create_products',
    'fn_update_products', 'fn_set_product_active',
    'fn_set_min_stock', 'fn_set_min_stock_batch',
    'fn_stock_panel', 'fn_company_stock_state',
    -- auxiliares usadas pelas policies e pela view
    'fn_current_user_id', 'fn_has_role', 'fn_is_member', 'fn_stock_state',
    -- Depois do login a aplicação precisa descobrir empresa e papel do
    -- usuário para montar a sessão e preencher `p_company_id` nas chamadas
    -- de catálogo. Sem esta, não há como sair da tela de login.
    'fn_my_companies',
    -- Movimentações (US03): o saldo é a soma das confirmadas.
    'fn_register_movement', 'fn_confirm_movement', 'fn_cancel_movement',
    'fn_confirmed_balance',
    'fn_list_company_clients', 'fn_create_client', 'fn_update_client',
    'fn_set_client_active', 'fn_register_sale',
    'fn_list_company_suppliers', 'fn_create_supplier', 'fn_update_supplier',
    'fn_set_supplier_active', 'fn_set_product_supplier',
    'fn_register_supplier_movement', 'fn_save_product', 'fn_save_company_member'
  ];
  v_name    text;
  v_sig     regprocedure;
  v_found   boolean;
  v_missing text[] := '{}';
BEGIN
  FOREACH v_name IN ARRAY v_names LOOP
    v_found := false;
    FOR v_sig IN SELECT p.oid::regprocedure FROM pg_proc p
                  WHERE p.pronamespace = 'public'::regnamespace AND p.proname = v_name
    LOOP
      EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO app_backend, authenticated', v_sig);
      v_found := true;
    END LOOP;
    IF NOT v_found THEN v_missing := v_missing || v_name; END IF;
  END LOOP;

  IF array_length(v_missing, 1) > 0 THEN
    RAISE EXCEPTION 'Funções obrigatórias ausentes: %', array_to_string(v_missing, ', ');
  END IF;
END $$;

-- Para funções criadas daqui em diante PELO PAPEL que aplica este arquivo.
-- Não cobre outro papel criador, e por isso NÃO substitui a varredura de
-- REVOKE acima: toda migration que criar função nova precisa repetir a
-- varredura. Foi exatamente esse o buraco de `fn_update_products`, criada por
-- uma migration posterior à de segurança e por isso nascida com EXECUTE para
-- PUBLIC — o anônimo conseguia chamá-la (e levava recusa de `fn_has_role`,
-- mas a camada de fora não deveria nem ter deixado chegar lá).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon;

-- PENDENTE: register/access_register não têm vínculo com company. Enquanto
-- isso não for resolvido, o caixa não é isolável por empresa e o backend não
-- lê essas tabelas via app_backend.


NOTIFY pgrst, 'reload schema';
