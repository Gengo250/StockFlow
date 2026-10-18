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
    v_new_balance integer;
    v_max_stock integer;
    v_company_limit integer;
    v_effective_max integer;
BEGIN
    -- 1. Calcula o novo saldo resultante das movimentações confirmadas
    v_new_balance := public.fn_confirmed_balance(v_product);

    -- 2. Busca os limites configurados (do produto e da empresa)
    SELECT ps.max_quantity, c.max_stock_limit
      INTO v_max_stock, v_company_limit
      FROM public.products p
      JOIN public.company c ON c.id = p.company_id
      LEFT JOIN public.product_stock ps ON ps.product_id = p.id
     WHERE p.id = v_product;

    -- O limite efetivo é o do produto; se o produto não tiver, é o da empresa
    v_effective_max := COALESCE(v_max_stock, v_company_limit);

    -- 3. Se o novo saldo ultrapassar o limite, aborta a transação
    IF v_effective_max IS NOT NULL AND v_new_balance > v_effective_max THEN
        RAISE EXCEPTION 'Movimentação rejeitada: o saldo resultante (%) ultrapassaria o estoque máximo permitido (%)',
            v_new_balance, v_effective_max
            USING ERRCODE = 'check_violation';
    END IF;

    -- 4. Atualiza o produto (se o saldo for negativo, o CHECK (stock >= 0) da tabela barra aqui)
    UPDATE public.products
       SET stock = v_new_balance
     WHERE id = v_product;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_stock_movements_apply ON public.stock_movements;
CREATE TRIGGER trg_stock_movements_apply
    AFTER INSERT OR UPDATE OR DELETE ON public.stock_movements
    FOR EACH ROW EXECUTE FUNCTION public.trg_stock_movements_apply();




CREATE OR REPLACE FUNCTION public.trg_check_product_max_stock()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company_id uuid;
    v_company_limit integer;
BEGIN
    -- Se max_quantity não foi informado, nada a validar
    IF NEW.max_quantity IS NULL THEN
        RETURN NEW;
    END IF;

    -- 1. Busca a empresa do produto e o teto da empresa
    SELECT p.company_id, c.max_stock_limit 
      INTO v_company_id, v_company_limit
      FROM public.products p
      JOIN public.company c ON c.id = p.company_id
     WHERE p.id = NEW.product_id;

    -- 2. Valida contra o teto da empresa
    IF v_company_limit IS NOT NULL AND NEW.max_quantity > v_company_limit THEN
        RAISE EXCEPTION 'O estoque máximo (%) excede o teto global configurado para a empresa (%)',
            NEW.max_quantity, v_company_limit
            USING ERRCODE = 'check_violation';
    END IF;

    -- 3. Garante que max_quantity >= min_quantity
    IF NEW.min_quantity IS NOT NULL AND NEW.max_quantity < NEW.min_quantity THEN
        RAISE EXCEPTION 'O estoque máximo (%) não pode ser inferior ao estoque mínimo (%)',
            NEW.max_quantity, NEW.min_quantity
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_check_product_max_stock ON public.product_stock;
CREATE TRIGGER trg_check_product_max_stock
    BEFORE INSERT OR UPDATE OF max_quantity, min_quantity
    ON public.product_stock
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_check_product_max_stock();