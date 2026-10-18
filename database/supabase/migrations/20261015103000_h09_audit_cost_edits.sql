-- H09: a auditoria de preço passa a cobrir o custo.
--
-- `price_edit_log` nasceu no remoto (20261013131814) e foi reconciliada em
-- 20261014120000 registrando apenas `sell_price`. Mexer no custo era a única
-- escrita de catálogo que ninguém conseguia reconstruir depois.
--
-- Esta migration estende uma tabela VIVA: o remoto já tem linhas gravadas, e
-- elas precisam continuar legíveis depois de a coluna do campo entrar. Por
-- isso nada aqui recria tabela e tudo é idempotente — `IF NOT EXISTS`, `DO`
-- com guarda e `DROP NOT NULL`, que é no-op sobre coluna que já aceita nulo.
--
-- A transação é aberta AQUI: `supabase db push` manda cada comando
-- separadamente, em autocommit, e sem o BEGIN uma falha no meio deixaria a
-- coluna sem o trigger que a preenche.

BEGIN;

DO $$
BEGIN
    IF to_regtype('public.price_edit_field') IS NULL THEN
        CREATE TYPE public.price_edit_field AS ENUM ('SELL_PRICE', 'BUY_PRICE');
    END IF;
END;
$$;

-- O DEFAULT é o que preenche as linhas que já existem: toda auditoria
-- gravada até aqui veio do preço de venda. Sem ele, `ADD COLUMN ... NOT NULL`
-- nem aplicaria sobre a tabela com dados.
ALTER TABLE public.price_edit_log
    ADD COLUMN IF NOT EXISTS field public.price_edit_field NOT NULL DEFAULT 'SELL_PRICE';

-- `products.buy_price` é nullable (tables/03_catalog.sql): informar o custo
-- pela primeira vez tem `OLD.buy_price IS NULL`. Com os dois lados
-- obrigatórios, o INSERT da auditoria violaria NOT NULL e derrubaria o UPDATE
-- do produto — a auditoria passaria a IMPEDIR a edição que ela registra.
ALTER TABLE public.price_edit_log ALTER COLUMN old_price DROP NOT NULL;
ALTER TABLE public.price_edit_log ALTER COLUMN new_price DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.price_edit_log'::regclass
                      AND conname = 'ck_price_edit_log_value_present') THEN
        ALTER TABLE public.price_edit_log
            ADD CONSTRAINT ck_price_edit_log_value_present
            CHECK (old_price IS NOT NULL OR new_price IS NOT NULL);
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.trg_log_price_edit()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    -- Um IF por campo, cada um comparando o SEU anterior com o SEU novo. Um
    -- IF só, disparado por qualquer um dos dois, gravaria a mudança de custo
    -- com os valores de preço: o log diria que algo mudou e mentiria sobre o
    -- quê. Quando os dois mudam no mesmo UPDATE, saem duas linhas.
    --
    -- IS DISTINCT FROM, e não <>, porque buy_price é nullable: `NULL <> 9` é
    -- NULL, e o IF não entraria justamente na primeira definição de custo.
    IF OLD.sell_price IS DISTINCT FROM NEW.sell_price THEN
        INSERT INTO public.price_edit_log (
            updated_by, company_id, field, old_price, new_price, product_id
        ) VALUES (
            public.fn_current_user_id(), NEW.company_id, 'SELL_PRICE',
            OLD.sell_price, NEW.sell_price, NEW.id
        );
    END IF;

    IF OLD.buy_price IS DISTINCT FROM NEW.buy_price THEN
        INSERT INTO public.price_edit_log (
            updated_by, company_id, field, old_price, new_price, product_id
        ) VALUES (
            public.fn_current_user_id(), NEW.company_id, 'BUY_PRICE',
            OLD.buy_price, NEW.buy_price, NEW.id
        );
    END IF;

    RETURN NEW;
END;
$$;

-- A lista de colunas faz parte do contrato: recriar só a função deixaria o
-- trigger surdo para `buy_price`, por mais completo que fosse o corpo acima.
DROP TRIGGER IF EXISTS trg_price_edit_log ON public.products;
CREATE TRIGGER trg_price_edit_log
    AFTER UPDATE OF sell_price, buy_price ON public.products
    FOR EACH ROW EXECUTE FUNCTION public.trg_log_price_edit();

REVOKE ALL ON FUNCTION public.trg_log_price_edit()
  FROM PUBLIC, anon, authenticated, app_backend;

NOTIFY pgrst, 'reload schema';

COMMIT;
