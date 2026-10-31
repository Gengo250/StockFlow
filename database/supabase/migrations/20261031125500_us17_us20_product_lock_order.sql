-- US17/US20/US22: ordena locks de produto por barcode ascendente nos fluxos
-- legados de cancelamento/devolução, igual ao checkout US22 e retorno US20.
-- Migration US17 20261024125000 já aplicada: corrigir com CREATE OR REPLACE
-- incremental, sem editar ou reparar histórico já registrado.
BEGIN;

CREATE OR REPLACE FUNCTION public.fn_cancel_sale(
    p_sale_id uuid,
    p_reason  text
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_status  public.sale_status;
    v_actor   uuid := public.fn_current_user_id();
    v_reason  text := btrim(COALESCE(p_reason, ''));
BEGIN
    SELECT s.company_id, s.status INTO v_company, v_status
      FROM public.sales s WHERE s.id = p_sale_id FOR UPDATE;
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Venda não encontrada ou sem permissão para cancelar'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF v_reason = '' THEN
        RAISE EXCEPTION 'Informe o motivo do cancelamento'
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_status <> 'CONCLUIDA' THEN
        RAISE EXCEPTION
            'Somente venda concluída pode ser cancelada (situação atual: %)',
            v_status USING ERRCODE = 'check_violation';
    END IF;

    -- Alinhar a ordem de locks de produto à US20/US22 antes de alterar
    -- movimentações, cujos triggers atualizam o saldo dos produtos.
    PERFORM p.id
      FROM public.products p
     WHERE p.company_id = v_company
       AND p.id IN (
           SELECT sm.product_id
             FROM public.stock_movements sm
            WHERE sm.sale_id = p_sale_id
              AND sm.status = 'CONFIRMADA'
              AND sm.product_id IS NOT NULL
       )
     ORDER BY p.barcode
     FOR UPDATE;

    INSERT INTO public.sale_reversals (company_id, sale_id, kind, reason, created_by)
    VALUES (v_company, p_sale_id, 'CANCELAMENTO', v_reason, v_actor);
    UPDATE public.stock_movements
       SET status = 'CANCELADA'
     WHERE sale_id = p_sale_id AND status = 'CONFIRMADA';
    UPDATE public.sales SET status = 'CANCELADA' WHERE id = p_sale_id;
    RETURN jsonb_build_object('sale_id', p_sale_id, 'kind', 'CANCELAMENTO',
                              'reason', v_reason, 'status', 'CANCELADA');
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_return_sale(
    p_sale_id uuid,
    p_reason  text
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_status  public.sale_status;
    v_actor   uuid := public.fn_current_user_id();
    v_reason  text := btrim(COALESCE(p_reason, ''));
    v_item    RECORD;
BEGIN
    SELECT s.company_id, s.status INTO v_company, v_status
      FROM public.sales s WHERE s.id = p_sale_id FOR UPDATE;
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Venda não encontrada ou sem permissão para devolver'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF v_reason = '' THEN
        RAISE EXCEPTION 'Informe o motivo da devolução'
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_status <> 'CONCLUIDA' THEN
        RAISE EXCEPTION
            'Somente venda concluída pode ser devolvida (situação atual: %)',
            v_status USING ERRCODE = 'check_violation';
    END IF;

    -- Pré-bloqueia todos os produtos na mesma ordem de US20/US22. Os INSERTs
    -- de movimentos abaixo podem atualizar saldos e precisam manter essa ordem.
    PERFORM p.id
      FROM public.products p
      JOIN public.sale_items i
        ON i.product_id = p.id AND i.company_id = p.company_id
     WHERE i.sale_id = p_sale_id
       AND p.company_id = v_company
     ORDER BY p.barcode
     FOR UPDATE;

    INSERT INTO public.sale_reversals (company_id, sale_id, kind, reason, created_by)
    VALUES (v_company, p_sale_id, 'DEVOLUCAO', v_reason, v_actor);

    FOR v_item IN
        SELECT i.product_id, i.quantity
          FROM public.sale_items i
          JOIN public.products p
            ON p.id = i.product_id AND p.company_id = i.company_id
         WHERE i.sale_id = p_sale_id
           AND i.product_id IS NOT NULL
           AND i.company_id = v_company
         ORDER BY p.barcode, i.id
    LOOP
        INSERT INTO public.stock_movements (
            company_id, product_id, sale_id, kind, quantity, status,
            note, created_by, confirmed_on
        ) VALUES (
            v_company, v_item.product_id, p_sale_id, 'ENTRADA',
            v_item.quantity, 'CONFIRMADA',
            'DEVOLUCAO_VENDA - venda ' || p_sale_id::text, v_actor, now()
        );
    END LOOP;
    UPDATE public.sales SET status = 'DEVOLVIDA' WHERE id = p_sale_id;
    RETURN jsonb_build_object('sale_id', p_sale_id, 'kind', 'DEVOLUCAO',
                              'reason', v_reason, 'status', 'DEVOLVIDA');
END;
$$;

REVOKE ALL ON FUNCTION public.fn_cancel_sale(uuid, text),
                          public.fn_return_sale(uuid, text)
    FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_cancel_sale(uuid, text),
                          public.fn_return_sale(uuid, text)
    TO app_backend, authenticated;

COMMIT;
