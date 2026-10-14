CREATE OR REPLACE FUNCTION public.fn_process_sale_completion()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_item RECORD;
BEGIN
    FOR v_item IN
        SELECT product_id, quantity
        FROM public.sale_items
        WHERE sale_id = NEW.id
          AND product_id IS NOT NULL
    LOOP
        INSERT INTO public.stock_movements (
            company_id,
            product_id,
            sale_id,
            kind,
            quantity,
            status,
            note,
            created_by,
            created_on
        ) VALUES (
            NEW.company_id,
            v_item.product_id,
            NEW.id,
            'SAIDA',
            v_item.quantity,
            'CONFIRMADA',
            'Venda concluida: ' || NEW.id::text,
            NEW.created_by,
            now()
        );
    END LOOP;

    IF NEW.payment_method = 'CASH' THEN
        UPDATE public.register
        SET change = COALESCE(change, 0) + NEW.total,
            logged_on = now()
        WHERE id = NEW.created_by
          AND company_id = NEW.company_id;
    END IF;

    RETURN NEW;
END;
$$;
