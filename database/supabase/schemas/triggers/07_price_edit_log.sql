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

DROP TRIGGER IF EXISTS trg_price_edit_log ON public.products;
-- A lista de colunas faz parte do contrato: sem `buy_price` aqui, o trigger
-- nem acorda numa edição que só mexeu no custo, por mais completo que seja
-- o corpo da função acima.
CREATE TRIGGER trg_price_edit_log
    AFTER UPDATE OF sell_price, buy_price ON public.products
    FOR EACH ROW EXECUTE FUNCTION public.trg_log_price_edit();
