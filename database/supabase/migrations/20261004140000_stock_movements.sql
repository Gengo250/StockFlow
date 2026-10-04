-- Movimentações de estoque: o saldo passa a ser a SOMA DAS CONFIRMADAS.
--
-- POR QUE
--
-- A US03 exige "considerar somente movimentações confirmadas na composição do
-- saldo". Até aqui `products.stock` era uma coluna inteira escrita direto por
-- `fn_create_products` e `fn_update_products`: não havia movimentação, não
-- havia o que confirmar, e não havia como auditar de onde o número veio.
--
-- Depois desta migration, `products.stock` continua existindo e continua sendo
-- o que todo mundo lê — mas ninguém mais escreve nele. Ele é mantido por
-- trigger a partir de `stock_movements`, e só as linhas CONFIRMADA contam.
-- A vantagem de manter a coluna, em vez de trocar tudo por uma soma na hora
-- da leitura: `vw_stock_situation`, `fn_stock_state` e a aplicação inteira
-- seguem funcionando sem alteração, e a soma não é refeita a cada consulta.
--
-- DUAS ESPÉCIES, NÃO TRÊS
--
-- ENTRADA e SAIDA, as duas com quantidade positiva. "Ajuste" não é uma
-- terceira espécie: é uma ENTRADA ou uma SAIDA com justificativa em `note`.
-- Um tipo AJUSTE de sinal variável exigiria afrouxar o CHECK de quantidade e
-- deixaria o sinal escondido no dado, onde ninguém lê.

-- =================================================================== tipos

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'movement_kind') THEN
    CREATE TYPE public.movement_kind AS ENUM ('ENTRADA', 'SAIDA');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'movement_status') THEN
    CREATE TYPE public.movement_status AS ENUM ('PENDENTE', 'CONFIRMADA', 'CANCELADA');
  END IF;
END $$;

-- ================================================================== tabela

CREATE TABLE public.stock_movements (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Redundante com `products.company_id`, e proposital: a policy de RLS
    -- escopa por esta coluna sem precisar entrar em `products` a cada linha.
    company_id   uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    product_id   uuid NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    kind         public.movement_kind   NOT NULL,
    quantity     integer NOT NULL CHECK (quantity > 0),
    -- Nasce PENDENTE: registrar não é confirmar. É essa distinção que a US03
    -- pede ao dizer "somente movimentações confirmadas".
    status       public.movement_status NOT NULL DEFAULT 'PENDENTE',
    note         text,
    created_by   uuid,
    created_on   timestamptz NOT NULL DEFAULT now(),
    confirmed_on timestamptz
);

CREATE INDEX idx_stock_movements_product
    ON public.stock_movements (product_id, status);
CREATE INDEX idx_stock_movements_company
    ON public.stock_movements (company_id);

-- ================================================= saldo a partir das linhas

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

-- ====================================================== carga inicial
--
-- ANTES do trigger, e só uma vez. Cada produto com saldo em `products.stock`
-- ganha uma ENTRADA confirmada equivalente, para que a soma das confirmadas
-- bata com o que já estava lá. Sem isto, o primeiro movimento de qualquer
-- produto zeraria o saldo histórico.
INSERT INTO public.stock_movements
       (company_id, product_id, kind, quantity, status, note, confirmed_on)
SELECT p.company_id, p.id, 'ENTRADA', p.stock, 'CONFIRMADA',
       'Saldo inicial migrado de products.stock', now()
  FROM public.products p
 WHERE p.stock > 0
   AND NOT EXISTS (SELECT 1 FROM public.stock_movements m WHERE m.product_id = p.id);

-- ================================================================= trigger

-- Recalcula o saldo do produto afetado a partir das confirmadas.
--
-- RECALCULA em vez de aplicar o delta: aplicar delta exige acertar todas as
-- transições (pendente->confirmada, confirmada->cancelada, exclusão, mudança
-- de quantidade), e qualquer caminho esquecido deixa o saldo em desacordo
-- com as linhas para sempre. Recalcular é auto-corretivo — o saldo nunca
-- diverge da soma, por construção.
--
-- O CHECK `stock >= 0` de `products` é o que impede uma SAIDA confirmada
-- maior que o saldo: o UPDATE falha e a transação inteira volta atrás.
CREATE OR REPLACE FUNCTION public.trg_stock_movements_apply()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_product uuid := COALESCE(NEW.product_id, OLD.product_id);
BEGIN
    UPDATE public.products
       SET stock = public.fn_confirmed_balance(v_product)
     WHERE id = v_product;

    -- UPDATE que troca o produto da linha precisa acertar os DOIS saldos.
    IF TG_OP = 'UPDATE' AND NEW.product_id IS DISTINCT FROM OLD.product_id THEN
        UPDATE public.products
           SET stock = public.fn_confirmed_balance(OLD.product_id)
         WHERE id = OLD.product_id;
    END IF;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_stock_movements_apply ON public.stock_movements;
CREATE TRIGGER trg_stock_movements_apply
    AFTER INSERT OR UPDATE OR DELETE ON public.stock_movements
    FOR EACH ROW EXECUTE FUNCTION public.trg_stock_movements_apply();

-- ================================================================ escrita

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
    IF NOT EXISTS (
        SELECT 1 FROM public.products
         WHERE id = p_product_id AND company_id = p_company_id
    ) THEN
        RAISE EXCEPTION 'Produto não encontrado nesta empresa'
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
BEGIN
    SELECT company_id, status INTO v_company, v_status
      FROM public.stock_movements WHERE id = p_movement_id;

    -- Mensagem única para inexistente e sem permissão: não vaza a existência
    -- de movimentações de outra empresa.
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Movimentação não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

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
BEGIN
    SELECT company_id INTO v_company
      FROM public.stock_movements WHERE id = p_movement_id;

    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Movimentação não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    UPDATE public.stock_movements
       SET status = 'CANCELADA'
     WHERE id = p_movement_id;
END;
$$;

-- ================================= cadastro e edição passam a movimentar
--
-- `fn_create_products` e `fn_update_products` escreviam `products.stock`
-- direto. Agora o saldo é consequência das movimentações, então as duas
-- registram uma movimentação CONFIRMADA em vez de tocar a coluna — senão o
-- trigger sobrescreveria o valor na próxima movimentação e o saldo "voltaria
-- no tempo" sem explicação.

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

-- ============================================== consulta de alerta (US04)
--
-- A US04 em uma consulta: produtos ATIVOS, com mínimo CONFIGURADO, cujo saldo
-- é menor ou igual a esse mínimo. O `<=` é o que inclui o saldo igual ao
-- mínimo; o `> 0` no mínimo é o que exclui quem não tem configuração.
CREATE OR REPLACE VIEW public.vw_stock_alerts
WITH (security_invoker = true) AS
SELECT
    s.company_id,
    s.product_id,
    s.product_name,
    s.current_balance,
    s.min_quantity,
    s.state
FROM public.vw_stock_situation s
WHERE s.min_quantity > 0
  AND s.current_balance <= s.min_quantity;

-- ============================================================= privilégios
--
-- Varredura + allowlist, repetidas aqui porque esta migration CRIA funções:
-- função nova nasce com EXECUTE para PUBLIC e escaparia do REVOKE das
-- migrations anteriores. Mesmo buraco que `fn_update_products` teve.

ALTER TABLE public.stock_movements ENABLE ROW LEVEL SECURITY;

GRANT SELECT ON public.stock_movements, public.vw_stock_alerts
  TO app_backend, authenticated;

DROP POLICY IF EXISTS stock_movements_select ON public.stock_movements;
CREATE POLICY stock_movements_select ON public.stock_movements
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT p.oid::regprocedure AS sig
             FROM pg_proc p
             JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.prokind = 'f'
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon', r.sig);
  END LOOP;
END $$;

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
    'fn_current_user_id', 'fn_has_role', 'fn_is_member', 'fn_stock_state',
    'fn_my_companies',
    'fn_register_movement', 'fn_confirm_movement', 'fn_cancel_movement',
    'fn_confirmed_balance'
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

-- ============================================================ conferência

DO $$
DECLARE
  v_divergentes text;
  v_abertas     text;
BEGIN
  -- O saldo de TODO produto precisa bater com a soma das confirmadas. É a
  -- afirmação que a US03 faz; se a carga inicial errou, falha agora.
  SELECT string_agg(p.barcode, ', ') INTO v_divergentes
    FROM public.products p
   WHERE p.stock IS DISTINCT FROM public.fn_confirmed_balance(p.id);

  IF v_divergentes IS NOT NULL THEN
    RAISE EXCEPTION 'Saldo não bate com as movimentações confirmadas em: %', v_divergentes;
  END IF;

  SELECT string_agg(DISTINCT p.proname, ', ') INTO v_abertas
    FROM pg_proc p
    CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) acl
   WHERE p.pronamespace = 'public'::regnamespace
     AND p.prokind = 'f'
     AND acl.privilege_type = 'EXECUTE'
     AND (acl.grantee = 0 OR pg_get_userbyid(acl.grantee) = 'anon');

  IF v_abertas IS NOT NULL THEN
    RAISE EXCEPTION 'Ainda executáveis por PUBLIC/anon: %', v_abertas;
  END IF;
END $$;
