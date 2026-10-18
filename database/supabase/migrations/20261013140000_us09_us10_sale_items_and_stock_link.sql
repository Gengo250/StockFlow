-- US09/US10: reconcilia tanto o schema US07 quanto o schema já aplicado
-- no remoto em 10-13/10/2026. Esta versão ainda NÃO havia sido aplicada.
-- Preserva vendas, itens, logs, autores e saldos; não usa DROP TABLE/CASCADE.
-- Quantidades históricas fracionárias causam recusa explícita, nunca
-- arredondamento ou exclusão silenciosa.
--
-- A transação é aberta AQUI, pelo próprio arquivo. `supabase db push` manda
-- cada comando da migration separadamente, em autocommit: sem este BEGIN o
-- LOCK abaixo é recusado com 25P01 ("LOCK TABLE can only be used in
-- transaction blocks") e a conversão de dados ficaria sem o rollback que os
-- comentários deste arquivo assumem.

BEGIN;

LOCK TABLE public.sales IN ACCESS EXCLUSIVE MODE;
DROP TRIGGER IF EXISTS trg_sale_completion ON public.sales;

DO $$
DECLARE
    v_old text;
    v_new text;
BEGIN
    IF to_regtype('public.sale_status') IS NULL THEN
        CREATE TYPE public.sale_status AS ENUM ('PENDENTE', 'CONCLUIDA', 'CANCELADA');
    ELSE
        FOR v_old, v_new IN SELECT * FROM (VALUES
            ('PENDING', 'PENDENTE'), ('COMPLETE', 'CONCLUIDA'), ('CANCELLED', 'CANCELADA')
        ) names LOOP
            IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'public.sale_status'::regtype AND enumlabel = v_old) THEN
                EXECUTE format('ALTER TYPE public.sale_status RENAME VALUE %L TO %L', v_old, v_new);
            END IF;
        END LOOP;
        ALTER TYPE public.sale_status ADD VALUE IF NOT EXISTS 'CANCELADA';
    END IF;
    IF to_regtype('public.payment_method') IS NULL THEN
        CREATE TYPE public.payment_method AS ENUM ('DINHEIRO', 'DEBITO', 'CREDITO', 'PIX', 'VALE', 'OUTRO');
    ELSE
        FOR v_old, v_new IN SELECT * FROM (VALUES
            ('CASH', 'DINHEIRO'), ('DEBIT', 'DEBITO'), ('CREDIT', 'CREDITO'),
            ('VOUCHER', 'VALE'), ('OTHER', 'OUTRO')
        ) names LOOP
            IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'public.payment_method'::regtype AND enumlabel = v_old) THEN
                EXECUTE format('ALTER TYPE public.payment_method RENAME VALUE %L TO %L', v_old, v_new);
            END IF;
        END LOOP;
    END IF;
END;
$$;

ALTER TABLE public.products ADD COLUMN IF NOT EXISTS updated_on timestamptz NOT NULL DEFAULT now();
ALTER TABLE public.products ADD COLUMN IF NOT EXISTS last_updated_by uuid;
DROP TRIGGER IF EXISTS trg_products_updated ON public.products;
CREATE TRIGGER trg_products_updated BEFORE UPDATE ON public.products
    FOR EACH ROW EXECUTE FUNCTION public.trg_set_updated_on();

-- No remoto customer_name era o snapshot; renomear conserva o texto exato.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='sales' AND column_name='client_name')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='sales' AND column_name='customer_name') THEN
        ALTER TABLE public.sales RENAME COLUMN customer_name TO client_name;
    END IF;
END;
$$;
ALTER TABLE public.sales ADD COLUMN IF NOT EXISTS client_name text;
UPDATE public.sales SET client_name = 'Consumidor' WHERE client_name IS NULL;
ALTER TABLE public.sales ALTER COLUMN client_name SET NOT NULL;
ALTER TABLE public.sales ADD COLUMN IF NOT EXISTS payment_method public.payment_method NOT NULL DEFAULT 'DINHEIRO';
ALTER TABLE public.sales ADD COLUMN IF NOT EXISTS discount numeric(10,2) NOT NULL DEFAULT 0 CHECK (discount >= 0);
ALTER TABLE public.sales ADD COLUMN IF NOT EXISTS status public.sale_status NOT NULL DEFAULT 'CONCLUIDA';
ALTER TABLE public.sales ALTER COLUMN status SET DEFAULT 'PENDENTE';
ALTER TABLE public.sales ALTER COLUMN payment_method SET DEFAULT 'DINHEIRO';

-- Autoria é user_accounts, não caixa. Valores históricos são preservados.
DO $$
DECLARE v_constraint text;
BEGIN
    FOR v_constraint IN SELECT conname FROM pg_constraint
      WHERE conrelid='public.sales'::regclass AND contype='f' AND confrelid='public.register'::regclass
    LOOP
        EXECUTE format('ALTER TABLE public.sales DROP CONSTRAINT %I', v_constraint);
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.sales'::regclass AND conname='sales_company_id_id_key') THEN
        ALTER TABLE public.sales ADD CONSTRAINT sales_company_id_id_key UNIQUE (company_id, id);
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS public.sale_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL,
    sale_id uuid NOT NULL,
    product_id uuid REFERENCES public.products(id) ON DELETE SET NULL,
    product_name text NOT NULL,
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(10,2) NOT NULL CHECK (unit_price >= 0),
    subtotal numeric(10,2) NOT NULL GENERATED ALWAYS AS (quantity * unit_price) STORED,
    created_on timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, sale_id) REFERENCES public.sales(company_id,id) ON DELETE CASCADE
);
LOCK TABLE public.sale_items IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.sale_items WHERE quantity <> trunc(quantity) OR quantity > 2147483647) THEN
        RAISE EXCEPTION 'Itens históricos com quantidade fracionária ou fora do limite; reconcilie antes de migrar';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='sale_items' AND column_name='quantity' AND data_type <> 'integer') THEN
        -- subtotal é calculado, não dado independente. Recriar a expressão
        -- é necessário para o PostgreSQL permitir mudar o tipo da quantidade.
        ALTER TABLE public.sale_items DROP COLUMN subtotal;
        ALTER TABLE public.sale_items ALTER COLUMN quantity TYPE integer USING quantity::integer;
        ALTER TABLE public.sale_items ADD COLUMN subtotal numeric(10,2)
            GENERATED ALWAYS AS (quantity * unit_price) STORED NOT NULL;
    END IF;
    -- O modelo US07 guardava o produto no cabeçalho. Conservar as colunas
    -- antigas como legado opcional após copiar, sem destruir snapshots.
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='sales' AND column_name='product_name') THEN
        INSERT INTO public.sale_items(company_id,sale_id,product_id,product_name,product_code,quantity,unit_price,created_on)
        SELECT s.company_id,s.id,s.product_id,s.product_name,s.product_code,1,s.total,s.created_on
          FROM public.sales s WHERE NOT EXISTS (SELECT 1 FROM public.sale_items i WHERE i.sale_id=s.id);
        ALTER TABLE public.sales ALTER COLUMN product_name DROP NOT NULL;
        ALTER TABLE public.sales ALTER COLUMN product_code DROP NOT NULL;
    END IF;
END;
$$;
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON public.sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_company ON public.sale_items(company_id);

CREATE TABLE IF NOT EXISTS public.sales_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    sale_id uuid NOT NULL REFERENCES public.sales(id) ON DELETE CASCADE,
    created_by uuid,
    logged_on timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.sales_log ADD COLUMN IF NOT EXISTS company_id uuid REFERENCES public.company(id) ON DELETE CASCADE;
UPDATE public.sales_log l SET company_id=s.company_id FROM public.sales s
 WHERE l.sale_id=s.id AND l.company_id IS NULL;
-- Log órfão interrompe a transação; não descartar uma evidência histórica.
ALTER TABLE public.sales_log ALTER COLUMN company_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sales_log_sale ON public.sales_log(sale_id);
ALTER TABLE public.stock_movements ADD COLUMN IF NOT EXISTS sale_id uuid REFERENCES public.sales(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_stock_movements_sale ON public.stock_movements(sale_id);

-- A assinatura remota antiga aponta para colunas inexistentes. Remover só
-- essa função inválida, sem CASCADE e sem tocar em dados.
DROP FUNCTION IF EXISTS public.fn_create_complete_sale(uuid,uuid,uuid,text,text,jsonb);



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
     FOR UPDATE;
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
    v_bruto       numeric := 0;
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
       OR p_discount >= 100000000 OR p_discount <> round(p_discount, 2)
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

    IF p_payment_method IS NULL THEN
        RAISE EXCEPTION 'Selecione uma forma de pagamento válida'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Trava TODOS os produtos em ordem estável antes de gravar. FOR SHARE
    -- deixava duas vendas travarem na conversão para UPDATE do saldo.
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
        IF jsonb_typeof(v_item) <> 'object'
           OR COALESCE(v_item->>'quantity', '') !~ '^[0-9]+$'
           OR (v_item->>'quantity')::numeric NOT BETWEEN 1 AND 1000000 THEN
            RAISE EXCEPTION 'Quantidade deve ser inteira entre 1 e 1000000'
                USING ERRCODE = 'check_violation';
        END IF;
    END LOOP;
    PERFORM p.id FROM public.products p
     WHERE p.company_id = p_company_id
       AND p.id IN (SELECT (i->>'product_id')::uuid FROM jsonb_array_elements(p_items) i)
     ORDER BY p.id FOR UPDATE;

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
         ;
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
        IF v_bruto >= 100000000 THEN
            RAISE EXCEPTION 'Total da venda acima do limite de R$ 99.999.999,99'
                USING ERRCODE = 'check_violation';
        END IF;
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

CREATE OR REPLACE FUNCTION public.fn_checkout_sale(
    p_company_id uuid,
    p_client_id uuid,
    p_items jsonb,
    p_payment_method public.payment_method DEFAULT 'DINHEIRO',
    p_discount numeric DEFAULT 0
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
    v_receipt jsonb;
BEGIN
    v_id := public.fn_create_complete_sale(
        p_company_id, p_client_id, p_items, p_payment_method, p_discount
    );
    SELECT to_jsonb(s) || jsonb_build_object('sale_items', (
        SELECT jsonb_agg(to_jsonb(i) ORDER BY i.created_on, i.id)
          FROM public.sale_items i WHERE i.sale_id = s.id
    )) INTO v_receipt FROM public.sales s WHERE s.id = v_id;
    RETURN v_receipt;
END;
$$;

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
    IF EXISTS (SELECT 1 FROM public.stock_movements
                WHERE id = p_movement_id AND sale_id IS NOT NULL) THEN
        RAISE EXCEPTION 'A saída pertence a uma venda e não pode ser cancelada isoladamente'
            USING ERRCODE = 'check_violation';
    END IF;
    UPDATE public.stock_movements
       SET status = 'CANCELADA'
     WHERE id = p_movement_id;
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

ALTER TABLE public.sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sale_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_log  ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.sales, public.sale_items, public.sales_log
    FROM PUBLIC, anon, authenticated, app_backend;

GRANT SELECT ON public.sales, public.sale_items, public.sales_log TO app_backend, authenticated;

DROP POLICY IF EXISTS sales_select ON public.sales;
CREATE POLICY sales_select ON public.sales FOR SELECT TO app_backend, authenticated USING (public.fn_is_member(company_id));

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
    'fn_register_sale', 'fn_create_complete_sale', 'fn_checkout_sale', 'fn_edit_product_stock', 'fn_cancel_movement'
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


-- Rotas antigas aceitam identidade enviada pelo cliente ou alteram saldo
-- diretamente. Preservar o histórico não significa manter essas portas.
DO $$
DECLARE v_sig regprocedure;
BEGIN
    FOR v_sig IN SELECT p.oid::regprocedure FROM pg_proc p
     WHERE p.pronamespace='public'::regnamespace
       AND (p.proname='fn_register_stock_entry' OR
            (p.proname='fn_edit_product_stock' AND p.pronargs=3))
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated, app_backend',v_sig);
    END LOOP;
END;
$$;

NOTIFY pgrst, 'reload schema';

COMMIT;
