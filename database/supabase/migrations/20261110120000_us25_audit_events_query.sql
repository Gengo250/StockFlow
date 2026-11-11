-- US25: consulta paginada de auditoria com filtros combináveis e ordenação.
--
-- Permite que auditores autorizados (ADMIN) investiguem operações por usuário,
-- período, ação e entidade, ordenando da mais recente para a mais antiga.
-- SECURITY DEFINER passa por cima da RLS, portanto a checagem de perfil (fn_is_admin)
-- é obrigatória para proteger o rastro de auditoria contra acessos não autorizados.

BEGIN;

CREATE OR REPLACE FUNCTION public.fn_list_audit_events(
    p_company_id uuid,
    p_product_id uuid DEFAULT NULL,
    p_user_name  text DEFAULT NULL,
    p_action     text DEFAULT NULL,
    p_entity     text DEFAULT NULL,
    p_from       timestamptz DEFAULT NULL,
    p_to         timestamptz DEFAULT NULL,
    p_sort       text DEFAULT 'DATA_DESC',
    p_limit      integer DEFAULT 50,
    p_offset     integer DEFAULT 0
)
RETURNS TABLE (
    id           uuid,
    changed_on   timestamptz,
    product_id   uuid,
    product_code text,
    product_name text,
    field        public.price_edit_field,
    old_price    numeric,
    new_price    numeric,
    changed_by   text,
    entity       text,
    total_count  bigint
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF NOT public.fn_is_admin(public.fn_current_user_id(), p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem consultar a auditoria'
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

    IF p_sort IS NULL OR p_sort NOT IN ('DATA_DESC', 'DATA_ASC') THEN
        RAISE EXCEPTION 'Ordenação desconhecida: %', p_sort
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN QUERY
    WITH filtradas AS (
        SELECT
            l.id,
            l.last_updated_on,
            l.product_id,
            COALESCE(p.barcode, '') AS product_code,
            COALESCE(p.name, '') AS product_name,
            l.field,
            l.old_price,
            l.new_price,
            COALESCE(ua.name, '') AS changed_by,
            'Produto'::text AS entity
          FROM public.price_edit_log l
          LEFT JOIN public.products      p  ON p.id  = l.product_id
          LEFT JOIN public.user_accounts ua ON ua.id = l.updated_by
         WHERE l.company_id = p_company_id
           AND (p_product_id IS NULL OR l.product_id = p_product_id)
           AND (p_user_name IS NULL OR lower(COALESCE(ua.name, '')) LIKE '%' || lower(btrim(p_user_name)) || '%')
           AND (p_action IS NULL OR l.field::text = p_action)
           AND (p_entity IS NULL OR lower(btrim(p_entity)) IN ('produto', 'produtos'))
           AND (p_from IS NULL OR l.last_updated_on >= p_from)
           AND (p_to IS NULL OR l.last_updated_on < p_to)
    )
    SELECT f.id,
           f.last_updated_on,
           f.product_id,
           f.product_code,
           f.product_name,
           f.field,
           f.old_price,
           f.new_price,
           f.changed_by,
           f.entity,
           count(*) OVER ()
      FROM filtradas f
     ORDER BY
        CASE WHEN p_sort = 'DATA_DESC' THEN f.last_updated_on END DESC,
        CASE WHEN p_sort = 'DATA_ASC'  THEN f.last_updated_on END ASC,
        f.id DESC
     LIMIT p_limit OFFSET p_offset;
END;
$$;

REVOKE ALL ON FUNCTION public.fn_list_audit_events(
    uuid, uuid, text, text, text, timestamptz, timestamptz, text, integer, integer
) FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.fn_list_audit_events(
    uuid, uuid, text, text, text, timestamptz, timestamptz, text, integer, integer
) TO app_backend, authenticated;

NOTIFY pgrst, 'reload schema';

COMMIT;
