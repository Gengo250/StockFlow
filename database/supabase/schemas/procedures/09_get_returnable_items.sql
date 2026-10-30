-- US20: elegibilidade calculada do histórico efetivado, sem contador redundante.
-- VOLATILE mantém visibilidade das devoluções feitas na mesma transação.
CREATE OR REPLACE FUNCTION public.fn_get_returnable_items(p_sale_id uuid)
RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_company uuid;
    v_status public.sale_status;
    v_result jsonb;
BEGIN
    IF public.fn_current_user_id() IS NULL THEN
        RAISE EXCEPTION 'Usuário responsável não identificado'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT s.company_id, s.status INTO v_company, v_status
      FROM public.sales s WHERE s.id = p_sale_id
       AND public.fn_has_role(s.company_id, ARRAY['ADMIN']::public.user_role[]);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Venda não encontrada ou sem permissão para devolver'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF v_status <> 'CONCLUIDA' THEN
        RAISE EXCEPTION 'Somente venda concluída pode ser consultada para devolução'
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
               'sale_item_id', si.id, 'product_id', si.product_id,
               'product_name', si.product_name, 'quantity_sold', si.quantity,
               'quantity_returned', returned.quantity,
               'max_returnable', si.quantity - returned.quantity
           ) ORDER BY si.id), '[]'::jsonb)
      INTO v_result
      FROM public.sale_items si
      CROSS JOIN LATERAL (
          SELECT COALESCE(sum(ri.quantity), 0) AS quantity
            FROM public.return_items ri JOIN public.returns r ON r.id = ri.return_id
           WHERE ri.company_id = v_company AND ri.sale_id = p_sale_id
             AND ri.sale_item_id = si.id AND r.status = 'COMPLETED'
      ) returned
     WHERE si.sale_id = p_sale_id AND si.company_id = v_company
       AND si.quantity > returned.quantity;
    -- Consulta informativa: a RPC de escrita revalida sob bloqueio.
    RETURN v_result;
END;
$$;

REVOKE ALL ON FUNCTION public.fn_get_returnable_items(uuid)
  FROM PUBLIC, anon, authenticated, app_backend;
