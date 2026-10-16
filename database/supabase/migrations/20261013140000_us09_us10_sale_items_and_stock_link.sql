-- US09 (edição de estoque) e US10 (venda com vários itens).
--
-- Substitui as 14 migrations do branch US09-US10, que criavam objetos e os
-- removiam poucas migrations depois. Nenhuma delas chegou ao banco: a de
-- `sales_log` referenciava `sales(created_by)`, coluna sem restrição única, e
-- `supabase db push` para ali com
--   there is no unique constraint matching given keys for referenced table
--
-- O que muda de verdade:
--   1. `sales` vira CABEÇALHO e os produtos vendidos passam para `sale_items`;
--   2. venda ganha forma de pagamento, desconto e situação;
--   3. concluir uma venda dá baixa no estoque POR MOVIMENTAÇÃO, respeitando a
--      regra da US03 de que saldo é a soma das confirmadas;
--   4. `products` passa a registrar quem alterou e quando.

-- ------------------------------------------------------------------- tipos

CREATE TYPE public.sale_status AS ENUM ('PENDENTE', 'CONCLUIDA', 'CANCELADA');

CREATE TYPE public.payment_method AS ENUM (
    'DINHEIRO', 'DEBITO', 'CREDITO', 'PIX', 'VALE', 'OUTRO'
);

-- ---------------------------------------------------------------- products

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS updated_on timestamptz NOT NULL DEFAULT now();
ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS last_updated_by uuid;

DROP TRIGGER IF EXISTS trg_products_updated ON public.products;
CREATE TRIGGER trg_products_updated BEFORE UPDATE ON public.products
    FOR EACH ROW EXECUTE FUNCTION public.trg_set_updated_on();

-- ------------------------------------------------- sales vira cabeçalho

ALTER TABLE public.sales
    ADD COLUMN IF NOT EXISTS payment_method public.payment_method
        NOT NULL DEFAULT 'DINHEIRO';
ALTER TABLE public.sales
    ADD COLUMN IF NOT EXISTS discount numeric(10,2) NOT NULL DEFAULT 0
        CHECK (discount >= 0);

-- As vendas que já existem são vendas fechadas, logo entram como CONCLUIDA.
-- Só depois o default vira PENDENTE, que é como venda nova nasce enquanto o
-- carrinho é montado.
ALTER TABLE public.sales
    ADD COLUMN IF NOT EXISTS status public.sale_status
        NOT NULL DEFAULT 'CONCLUIDA';
ALTER TABLE public.sales ALTER COLUMN status SET DEFAULT 'PENDENTE';

-- Alvo da FK composta de sale_items: item e venda na mesma empresa.
ALTER TABLE public.sales DROP CONSTRAINT IF EXISTS sales_company_id_id_key;
ALTER TABLE public.sales
    ADD CONSTRAINT sales_company_id_id_key UNIQUE (company_id, id);

-- ------------------------------------------------------------ sale_items

DROP TABLE IF EXISTS public.sale_items CASCADE;
CREATE TABLE public.sale_items (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL,
    sale_id       uuid NOT NULL,
    product_id    uuid,
    product_name  text NOT NULL,
    product_code  text NOT NULL,
    quantity      integer NOT NULL CHECK (quantity > 0),
    unit_price    numeric(10,2) NOT NULL CHECK (unit_price >= 0),
    subtotal      numeric(10,2) NOT NULL
                  GENERATED ALWAYS AS (quantity * unit_price) STORED,
    created_on    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE CASCADE,
    FOREIGN KEY (product_id)
        REFERENCES public.products (id) ON DELETE SET NULL
);
CREATE INDEX idx_sale_items_sale ON public.sale_items (sale_id);
CREATE INDEX idx_sale_items_company ON public.sale_items (company_id);

-- Cada venda antiga tinha um produto só: vira um item de quantidade 1 cujo
-- preço unitário é o total que foi cobrado. Sem este passo o histórico
-- existente ficaria sem nenhum item.
INSERT INTO public.sale_items (
    company_id, sale_id, product_id, product_name, product_code,
    quantity, unit_price, created_on
)
SELECT company_id, id, product_id, product_name, product_code,
       1, total, created_on
  FROM public.sales;

ALTER TABLE public.sales DROP COLUMN IF EXISTS product_id;
ALTER TABLE public.sales DROP COLUMN IF EXISTS product_name;
ALTER TABLE public.sales DROP COLUMN IF EXISTS product_code;

-- ------------------------------------------------------------- sales_log

DROP TABLE IF EXISTS public.sales_log CASCADE;
CREATE TABLE public.sales_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    sale_id     uuid NOT NULL REFERENCES public.sales(id) ON DELETE CASCADE,
    created_by  uuid,
    logged_on   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_sales_log_sale ON public.sales_log (sale_id);

-- ------------------------------------------- movimentação sabe da venda

ALTER TABLE public.stock_movements
    ADD COLUMN IF NOT EXISTS sale_id uuid
        REFERENCES public.sales(id) ON DELETE SET NULL;
DROP INDEX IF EXISTS public.idx_stock_movements_sale;
CREATE INDEX idx_stock_movements_sale ON public.stock_movements (sale_id);

-- ------------------------------------------------------------ rotinas
--
-- Copiadas de database/code: a fonte declarativa é quem manda, e texto
-- reescrito à mão aqui já divergiu da fonte antes.

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
        company_id, client_id, client_name, total, created_by
    ) VALUES (
        p_company_id, p_client_id, v_client_name, p_total,
        public.fn_current_user_id()
    )
    RETURNING id INTO v_id;

    INSERT INTO public.sale_items (
        company_id, sale_id, product_id, product_name, product_code,
        quantity, unit_price
    ) VALUES (
        p_company_id, v_id, p_product_id, v_product_name,
        COALESCE(v_product_code, ''), 1, p_total
    );

    UPDATE public.sales SET status = 'CONCLUIDA' WHERE id = v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_complete_sale(
    p_company_id     uuid,
    p_client_id      uuid,
    p_items          jsonb,
    p_payment_method public.payment_method DEFAULT 'DINHEIRO',
    p_discount       numeric DEFAULT 0
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id          uuid;
    v_client_name text;
    v_item        jsonb;
    v_product_id  uuid;
    v_quantity    integer;
    v_name        text;
    v_code        text;
    v_price       numeric(10,2);
    v_bruto       numeric(10,2) := 0;
    v_total       numeric(10,2);
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','SELLER']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para registrar vendas nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array'
       OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'Venda sem itens' USING ERRCODE = 'check_violation';
    END IF;

    IF p_discount IS NULL OR p_discount < 0
       OR p_discount::text IN ('NaN', 'Infinity', '-Infinity') THEN
        RAISE EXCEPTION 'Desconto inválido' USING ERRCODE = 'check_violation';
    END IF;

    SELECT name INTO v_client_name
      FROM public.clients
     WHERE id = p_client_id AND company_id = p_company_id AND active
     FOR SHARE;
    IF v_client_name IS NULL THEN
        RAISE EXCEPTION 'Cliente não encontrado, inativo ou sem permissão'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO public.sales (
        company_id, client_id, client_name, payment_method, discount,
        total, created_by
    ) VALUES (
        p_company_id, p_client_id, v_client_name, p_payment_method, p_discount,
        0, public.fn_current_user_id()
    )
    RETURNING id INTO v_id;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
        v_product_id := NULLIF(v_item->>'product_id', '')::uuid;
        v_quantity   := COALESCE((v_item->>'quantity')::integer, 0);

        IF v_quantity <= 0 THEN
            RAISE EXCEPTION 'Quantidade deve ser maior que zero (recebida: %)', v_quantity
                USING ERRCODE = 'check_violation';
        END IF;

        -- Preço, nome e código vêm do catálogo DESTA empresa. Produto de
        -- outra empresa não é encontrado aqui, e é esse filtro que impede
        -- vender item alheio informando o id.
        SELECT name, barcode, sell_price INTO v_name, v_code, v_price
          FROM public.products
         WHERE id = v_product_id AND company_id = p_company_id AND active
         FOR SHARE;
        IF v_name IS NULL THEN
            RAISE EXCEPTION 'Produto não encontrado, inativo ou sem permissão: %', v_product_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;

        INSERT INTO public.sale_items (
            company_id, sale_id, product_id, product_name, product_code,
            quantity, unit_price
        ) VALUES (
            p_company_id, v_id, v_product_id, v_name, COALESCE(v_code, ''),
            v_quantity, v_price
        );

        v_bruto := v_bruto + (v_quantity * v_price);
    END LOOP;

    v_total := v_bruto - p_discount;
    IF v_total < 0 THEN
        RAISE EXCEPTION 'Desconto (%) maior que o total dos itens (%)', p_discount, v_bruto
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.sales
       SET total = v_total, status = 'CONCLUIDA'
     WHERE id = v_id;

    RETURN v_id;
END;
$$;

-- Edição de estoque pelo código de barras (US09).
--
-- É um ATALHO sobre fn_register_movement, não um caminho paralelo: escrever
-- `products.stock` aqui seria desfeito pelo recálculo do trigger de
-- triggers/04 na movimentação seguinte, e o saldo passaria a depender de qual
-- caminho foi usado por último.
--
-- Não recebe o usuário por parâmetro de propósito: a autoria sai de
-- fn_current_user_id(), como em todo o resto desta árvore. Recebê-lo deixaria
-- o chamador registrar a alteração em nome de outra pessoa.
--
-- `p_company_id` é obrigatório porque barcode só é único DENTRO da empresa
-- (UNIQUE (company_id, barcode) em tables/03_catalog.sql).
CREATE OR REPLACE FUNCTION public.fn_edit_product_stock(
    p_company_id uuid,
    p_barcode    text,
    p_quantity   integer,
    p_note       text DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_product_id uuid;
    v_movement   uuid;
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantidade deve ser maior que zero (recebida: %)', p_quantity
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT id INTO v_product_id
      FROM public.products
     WHERE company_id = p_company_id AND barcode = p_barcode AND active;
    IF v_product_id IS NULL THEN
        RAISE EXCEPTION 'Produto não encontrado ou inativo nesta empresa: %', p_barcode
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- A permissão (ADMIN/STOCK) e o vínculo produto-empresa são conferidos
    -- aqui dentro; repetir a checagem antes seria uma segunda regra para
    -- manter em dia.
    v_movement := public.fn_register_movement(
        p_company_id, v_product_id, 'ENTRADA', p_quantity,
        COALESCE(p_note, 'Entrada manual de estoque'), true);

    UPDATE public.products
       SET last_updated_by = public.fn_current_user_id()
     WHERE id = v_product_id;

    RETURN v_movement;
END;
$$;

-- Conclusão de venda: carimba o log e dá baixa no estoque.
--
-- A baixa é feita REGISTRANDO MOVIMENTAÇÃO, nunca escrevendo products.stock:
-- o saldo desta árvore é a soma das movimentações confirmadas
-- (procedures/04a_movements.sql), e quem escrevesse o saldo direto seria
-- sobrescrito pelo recálculo do trigger de triggers/04 na movimentação
-- seguinte.
--
-- Dispara na TRANSIÇÃO para CONCLUIDA, e não no INSERT: a venda nasce
-- PENDENTE enquanto o carrinho é montado, e só o fechamento tira produto da
-- prateleira.
--
-- O caixa (tables/02_cash_register.sql) fica DE FORA de propósito: `register`
-- não tem company_id, então creditar a venda nele não teria como ser escopado
-- por empresa. Ver a nota PENDENTE no fim de policies/01_security.sql.
CREATE OR REPLACE FUNCTION public.fn_process_sale_completion()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_item    RECORD;
    v_balance integer;
BEGIN
    INSERT INTO public.sales_log (company_id, sale_id, created_by)
    VALUES (NEW.company_id, NEW.id, NEW.created_by);

    FOR v_item IN
        SELECT product_id, product_name, quantity
          FROM public.sale_items
         WHERE sale_id = NEW.id AND product_id IS NOT NULL
    LOOP
        -- Conferência explícita antes de inserir. Sem ela a falta de estoque
        -- apareceria como violação do CHECK `stock >= 0` de products, com
        -- mensagem que não diz qual produto faltou.
        v_balance := public.fn_confirmed_balance(v_item.product_id);
        IF v_balance < v_item.quantity THEN
            RAISE EXCEPTION
                'Estoque insuficiente para % (disponível: %, vendido: %)',
                v_item.product_name, v_balance, v_item.quantity
                USING ERRCODE = 'check_violation';
        END IF;

        INSERT INTO public.stock_movements (
            company_id, product_id, sale_id, kind, quantity, status,
            note, created_by, confirmed_on
        ) VALUES (
            NEW.company_id, v_item.product_id, NEW.id, 'SAIDA',
            v_item.quantity, 'CONFIRMADA',
            'Venda ' || NEW.id::text, NEW.created_by, now()
        );
    END LOOP;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_sale_completion ON public.sales;
CREATE TRIGGER trg_sale_completion
    AFTER UPDATE OF status ON public.sales
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'CONCLUIDA')
    EXECUTE FUNCTION public.fn_process_sale_completion();

-- ---------------------------------------------------------------- segurança
--
-- Repete a varredura de REVOKE de policies/01_security.sql de propósito: o
-- ALTER DEFAULT PRIVILEGES de lá só alcança funções criadas pelo MESMO papel
-- que aplicou aquele arquivo. Foi esse buraco que fez `fn_update_products`
-- nascer com EXECUTE para PUBLIC.

ALTER TABLE public.sale_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_log  ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.sale_items, public.sales_log
    FROM PUBLIC, anon, authenticated, app_backend;

GRANT SELECT ON public.sale_items, public.sales_log TO app_backend, authenticated;

DROP POLICY IF EXISTS sale_items_select ON public.sale_items;
CREATE POLICY sale_items_select ON public.sale_items
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

DROP POLICY IF EXISTS sales_log_select ON public.sales_log;
CREATE POLICY sales_log_select ON public.sales_log
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

DO $$
DECLARE
  v_names text[] := ARRAY[
    'fn_register_sale', 'fn_create_complete_sale', 'fn_edit_product_stock'
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
      EXECUTE format(
        'REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated, app_backend', v_sig);
      EXECUTE format(
        'GRANT EXECUTE ON FUNCTION %s TO app_backend, authenticated', v_sig);
      v_found := true;
    END LOOP;
    IF NOT v_found THEN v_missing := v_missing || v_name; END IF;
  END LOOP;

  IF array_length(v_missing, 1) > 0 THEN
    RAISE EXCEPTION 'Funções obrigatórias ausentes: %', array_to_string(v_missing, ', ');
  END IF;
END $$;

-- fn_process_sale_completion fica FORA da lista acima de propósito: ela só é
-- chamada pelo trigger, como dona da função (SECURITY DEFINER). Dar EXECUTE a
-- app_backend deixaria o backend carimbar sales_log e criar movimentação sem
-- passar por venda nenhuma.
REVOKE ALL ON FUNCTION public.fn_process_sale_completion()
    FROM PUBLIC, anon, authenticated, app_backend;
