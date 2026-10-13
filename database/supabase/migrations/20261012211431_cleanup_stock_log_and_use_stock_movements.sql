ALTER TABLE public.stock_movements
ADD COLUMN IF NOT EXISTS sale_id uuid REFERENCES public.sales(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_stock_movements_sale_id ON public.stock_movements(sale_id);

CREATE OR REPLACE FUNCTION public.fn_register_stock_entry(
    p_company_id  uuid,
    p_product_id  uuid,
    p_quantity    numeric,
    p_user_id     uuid,
    p_supplier_id uuid DEFAULT NULL,
    p_note        text DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_movement_id uuid;
    v_product_exists boolean;
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'A quantidade de entrada deve ser maior que zero (recebido: %)', p_quantity;
    END IF;

    SELECT EXISTS (
        SELECT 1 
        FROM public.products 
        WHERE id = p_product_id 
          AND company_id = p_company_id
    ) INTO v_product_exists;

    IF NOT v_product_exists THEN
        RAISE EXCEPTION 'Produto % nao encontrado para a empresa %', p_product_id, p_company_id;
    END IF;

    INSERT INTO public.stock_movements (
        company_id,
        product_id,
        supplier_id,
        kind,
        quantity,
        status,
        note,
        created_by,
        created_on
    ) VALUES (
        p_company_id,
        p_product_id,
        p_supplier_id,
        'ENTRADA',
        p_quantity,
        'CONFIRMADA',
        COALESCE(p_note, 'Entrada manual de estoque'),
        p_user_id,
        now()
    )
    RETURNING id INTO v_movement_id;

    RETURN v_movement_id;
END;
$$;

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
            NEW.register_id,
            now()
        );
    END LOOP;

    IF NEW.payment_method = 'CASH' THEN
        UPDATE public.register
        SET change = COALESCE(change, 0) + NEW.total,
            logged_on = now()
        WHERE id = NEW.register_id
          AND company_id = NEW.company_id;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sale_completion ON public.sales;
DROP TRIGGER IF EXISTS trg_sale_stock_reduction ON public.sales;

CREATE TRIGGER trg_sale_completion
AFTER UPDATE OF status ON public.sales
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'COMPLETE')
EXECUTE FUNCTION public.fn_process_sale_completion();
