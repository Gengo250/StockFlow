-- US17: por padrão, listar vendas finalizadas, sem perder a consulta explícita
-- de registros PENDENTE legados ou de fluxos futuros.
CREATE OR REPLACE FUNCTION public.fn_list_sales(
    p_company_id uuid,
    p_sale_id    text               DEFAULT NULL,
    p_from       timestamptz        DEFAULT NULL,
    p_to         timestamptz        DEFAULT NULL,
    p_client_id  uuid               DEFAULT NULL,
    p_seller_id  uuid               DEFAULT NULL,
    p_status     public.sale_status DEFAULT NULL,
    p_sort       text               DEFAULT 'DATA_DESC',
    p_limit      integer            DEFAULT 50,
    p_offset     integer            DEFAULT 0
)
RETURNS TABLE (
    id               uuid,
    client_id        uuid,
    client_name      text,
    seller_id        uuid,
    seller_name      text,
    payment_method   public.payment_method,
    discount         numeric,
    total            numeric,
    status           public.sale_status,
    created_on       timestamptz,
    items            jsonb,
    reversal_kind    public.sale_reversal_kind,
    reversal_reason  text,
    reversal_on      timestamptz,
    reversal_by_name text,
    total_count      bigint
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $fn_list_sales$
BEGIN
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Sem permissão para consultar o histórico desta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF p_limit IS NULL OR p_limit <= 0 OR p_limit > 200 THEN
        RAISE EXCEPTION 'Tamanho de página inválido: %', p_limit
            USING ERRCODE = 'check_violation';
    END IF;
    IF p_offset IS NULL OR p_offset < 0 THEN
        RAISE EXCEPTION 'Deslocamento de página inválido: %', p_offset
            USING ERRCODE = 'check_violation';
    END IF;
    IF p_sort IS NULL OR p_sort NOT IN
       ('DATA_DESC', 'DATA_ASC', 'VALOR_DESC', 'VALOR_ASC', 'CLIENTE_ASC') THEN
        RAISE EXCEPTION 'Ordenação desconhecida: %', p_sort
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN QUERY
    WITH filtradas AS (
        SELECT s.*
          FROM public.sales s
         WHERE s.company_id = p_company_id
           AND (p_sale_id   IS NULL OR s.id::text LIKE lower(btrim(p_sale_id)) || '%')
           AND (p_from      IS NULL OR s.created_on >= p_from)
           AND (p_to        IS NULL OR s.created_on < p_to)
           AND (p_client_id IS NULL OR s.client_id = p_client_id)
           AND (p_seller_id IS NULL OR s.created_by = p_seller_id)
           -- Sem um status explícito, o histórico contém apenas vendas
           -- finalizadas. PENDENTE continua consultável quando selecionada.
           AND (p_status IS NOT NULL OR s.status <> 'PENDENTE')
           AND (p_status    IS NULL OR s.status = p_status)
    )
    SELECT f.id,
           f.client_id,
           f.client_name,
           f.created_by,
           COALESCE(ua.name, ''),
           f.payment_method,
           f.discount,
           f.total,
           f.status,
           f.created_on,
           COALESCE((SELECT jsonb_agg(to_jsonb(i) ORDER BY i.created_on, i.id)
                       FROM public.sale_items i
                      WHERE i.sale_id = f.id), '[]'::jsonb),
           r.kind,
           r.reason,
           r.created_on,
           COALESCE(rua.name, ''),
           count(*) OVER ()
      FROM filtradas f
      LEFT JOIN public.sale_reversals r   ON r.sale_id = f.id
      LEFT JOIN public.user_accounts  ua  ON ua.id = f.created_by
      LEFT JOIN public.user_accounts  rua ON rua.id = r.created_by
     ORDER BY
        CASE WHEN p_sort = 'DATA_DESC'   THEN f.created_on END DESC,
        CASE WHEN p_sort = 'DATA_ASC'    THEN f.created_on END ASC,
        CASE WHEN p_sort = 'VALOR_DESC'  THEN f.total      END DESC,
        CASE WHEN p_sort = 'VALOR_ASC'   THEN f.total      END ASC,
        CASE WHEN p_sort = 'CLIENTE_ASC' THEN lower(f.client_name) END ASC,
        f.id DESC
     LIMIT p_limit OFFSET p_offset;
END;
$fn_list_sales$;
