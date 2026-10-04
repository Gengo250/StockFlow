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
