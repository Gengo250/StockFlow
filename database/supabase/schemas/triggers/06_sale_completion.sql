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
