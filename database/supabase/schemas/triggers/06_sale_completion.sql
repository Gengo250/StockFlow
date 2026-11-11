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
-- A sessão de caixa é validada por trg_validate_sale_open_register. Este
-- trigger só registra a conclusão e o estoque; não faz liquidação financeira.
-- US15: toda nova saída identifica o item, sem backfill das saídas legadas.
CREATE OR REPLACE FUNCTION public.fn_process_sale_completion()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_item    RECORD;
    v_balance integer;
BEGIN
    IF OLD.status <> 'PENDENTE' THEN
        RAISE EXCEPTION 'Somente venda pendente pode ser concluída'
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM i.id FROM public.sale_items i
     WHERE i.sale_id = NEW.id ORDER BY i.id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Venda sem itens; conclusão recusada'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.sale_items i
        LEFT JOIN public.products p
          ON p.id = i.product_id AND p.company_id = NEW.company_id
        WHERE i.sale_id = NEW.id
          AND (i.company_id <> NEW.company_id OR p.id IS NULL)
    ) OR EXISTS (
        SELECT 1 FROM public.stock_movements sm
         WHERE sm.sale_id = NEW.id AND sm.status = 'CONFIRMADA'
    ) THEN
        RAISE EXCEPTION 'Inconsistência nos itens ou movimentações da venda; conclusão recusada'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Também protege transições diretas: não depender só dos locks do checkout.
    PERFORM p.id FROM public.products p
     WHERE p.company_id = NEW.company_id
       AND p.id IN (SELECT i.product_id FROM public.sale_items i WHERE i.sale_id = NEW.id)
     ORDER BY p.barcode FOR UPDATE;

    INSERT INTO public.sales_log (company_id, sale_id, created_by)
    VALUES (NEW.company_id, NEW.id, NEW.created_by);

    FOR v_item IN
        SELECT i.id, i.product_id, i.product_name, i.quantity
          FROM public.sale_items i
          JOIN public.products p ON p.id = i.product_id AND p.company_id = i.company_id
         WHERE i.sale_id = NEW.id AND i.company_id = NEW.company_id
         ORDER BY p.barcode, i.id
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
            company_id, product_id, sale_id, sale_item_id, kind, quantity, status,
            note, created_by, confirmed_on
        ) VALUES (
            NEW.company_id, v_item.product_id, NEW.id, v_item.id, 'SAIDA',
            v_item.quantity, 'CONFIRMADA',
            'SAIDA_VENDA - venda ' || NEW.id::text, NEW.created_by, now()
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
