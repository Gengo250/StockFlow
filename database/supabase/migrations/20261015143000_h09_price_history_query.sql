-- H09: consulta cronológica do histórico de preço e custo.
--
-- Depende de `public.price_edit_field`, criado em 20261015103000: a função
-- devolve a coluna `field`, então aplicar esta antes daquela falharia.
--
-- Só cria função, mas abre transação assim mesmo: `supabase db push` manda
-- cada comando em autocommit, e sem o BEGIN uma falha entre o CREATE e o
-- GRANT deixaria a função aplicada e inalcançável pelo app.

BEGIN;

CREATE OR REPLACE FUNCTION public.fn_list_price_edits(
    p_company_id uuid,
    p_product_id uuid DEFAULT NULL
)
RETURNS TABLE (
    changed_on   timestamptz,
    product_id   uuid,
    product_code text,
    product_name text,
    field        public.price_edit_field,
    old_price    numeric,
    new_price    numeric,
    changed_by   text
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    -- SECURITY DEFINER passa por cima da RLS, então a checagem que
    -- `price_edit_log_select` faz na tabela precisa ser repetida aqui. Sem
    -- ela, esta função vira a porta dos fundos da própria auditoria.
    IF NOT public.fn_is_admin(public.fn_current_user_id(), p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem consultar o histórico de preços'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN QUERY
    SELECT
        l.last_updated_on,
        l.product_id,
        COALESCE(p.barcode, ''),
        COALESCE(p.name, ''),
        l.field,
        l.old_price,
        l.new_price,
        COALESCE(ua.name, '')
      FROM public.price_edit_log l
      LEFT JOIN public.products      p  ON p.id  = l.product_id
      LEFT JOIN public.user_accounts ua ON ua.id = l.updated_by
     WHERE l.company_id = p_company_id
       AND (p_product_id IS NULL OR l.product_id = p_product_id)
     ORDER BY l.last_updated_on DESC, l.id DESC;
END;
$$;

-- A varredura de permissão. Função nova nasce com EXECUTE para PUBLIC, e
-- `database/code/policies/01_security.sql` registra esse buraco pelo nome:
-- foi assim que `fn_update_products` ficou chamável pelo anônimo.
REVOKE ALL ON FUNCTION public.fn_list_price_edits(uuid, uuid)
  FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.fn_list_price_edits(uuid, uuid)
  TO app_backend, authenticated;

NOTIFY pgrst, 'reload schema';

COMMIT;
