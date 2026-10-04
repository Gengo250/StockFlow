-- Registro e confirmação de movimentações. Depende de stock_movements
-- (tables/05) e de fn_has_role (02_authz).
--
-- Vem depois de 04_stock e antes de 05_catalog porque `fn_create_products` e
-- `fn_update_products` passaram a registrar movimentação em vez de escrever
-- `products.stock`.

-- Saldo confirmado de um produto. Uma função, e não a expressão repetida no
-- trigger e na carga inicial: duas cópias da mesma soma divergem, e a
-- divergência aqui significa saldo errado na tela.
-- VOLATILE, e não STABLE: ela é chamada de dentro de um trigger AFTER, onde
-- precisa enxergar a linha que acabou de ser gravada. STABLE amarra a função
-- ao snapshot da consulta chamadora, e um saldo calculado sobre o estado
-- ANTERIOR ficaria errado por uma movimentação a cada vez — erro que só
-- apareceria em produção, somando silenciosamente. O custo é perder inlining
-- numa função que só o trigger e a conferência usam.
CREATE OR REPLACE FUNCTION public.fn_confirmed_balance(p_product_id uuid)
RETURNS integer
LANGUAGE sql VOLATILE
SET search_path = public AS $$
    SELECT COALESCE(SUM(
        CASE m.kind WHEN 'ENTRADA' THEN m.quantity ELSE -m.quantity END
    ), 0)::integer
      FROM public.stock_movements m
     WHERE m.product_id = p_product_id
       AND m.status = 'CONFIRMADA';
$$;

-- Registra uma movimentação. Nasce PENDENTE salvo pedido explícito.
CREATE OR REPLACE FUNCTION public.fn_register_movement(
    p_company_id uuid,
    p_product_id uuid,
    p_kind       public.movement_kind,
    p_quantity   integer,
    p_note       text    DEFAULT NULL,
    p_confirm    boolean DEFAULT false
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para movimentar estoque nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantidade deve ser maior que zero (recebida: %)', p_quantity
            USING ERRCODE = 'check_violation';
    END IF;

    -- O produto precisa ser DA empresa informada. Sem esta checagem, quem é
    -- STOCK numa empresa movimentaria o estoque de outra.
    IF NOT EXISTS (
        SELECT 1 FROM public.products
         WHERE id = p_product_id AND company_id = p_company_id
    ) THEN
        RAISE EXCEPTION 'Produto não encontrado nesta empresa'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO public.stock_movements
           (company_id, product_id, kind, quantity, status, note,
            created_by, confirmed_on)
    VALUES (p_company_id, p_product_id, p_kind, p_quantity,
            CASE WHEN p_confirm THEN 'CONFIRMADA' ELSE 'PENDENTE' END::public.movement_status,
            p_note, public.fn_current_user_id(),
            CASE WHEN p_confirm THEN now() END)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

-- Confirma uma movimentação pendente. É esta transição que muda o saldo.
CREATE OR REPLACE FUNCTION public.fn_confirm_movement(p_movement_id uuid)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_status  public.movement_status;
BEGIN
    SELECT company_id, status INTO v_company, v_status
      FROM public.stock_movements WHERE id = p_movement_id;

    -- Mensagem única para inexistente e sem permissão: não vaza a existência
    -- de movimentações de outra empresa.
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Movimentação não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF v_status <> 'PENDENTE' THEN
        RAISE EXCEPTION 'Só movimentação pendente pode ser confirmada (situação atual: %)', v_status
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.stock_movements
       SET status = 'CONFIRMADA', confirmed_on = now()
     WHERE id = p_movement_id;
END;
$$;

-- Cancela. Cancelar uma CONFIRMADA desfaz o efeito dela no saldo, porque o
-- trigger recalcula a soma das que seguem confirmadas.
CREATE OR REPLACE FUNCTION public.fn_cancel_movement(p_movement_id uuid)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
BEGIN
    SELECT company_id INTO v_company
      FROM public.stock_movements WHERE id = p_movement_id;

    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Movimentação não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    UPDATE public.stock_movements
       SET status = 'CANCELADA'
     WHERE id = p_movement_id;
END;
$$;
