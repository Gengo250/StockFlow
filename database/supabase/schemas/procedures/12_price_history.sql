-- Consulta cronológica do histórico de preço e custo (H09).
--
-- Mora numa função, e não num SELECT da tela, pela mesma razão de
-- `fn_list_company_users`: a linha de auditoria guarda ids, e a pergunta do
-- usuário é sobre nomes — qual produto, quem mexeu. O join vive aqui, uma vez,
-- em vez de ser reescrito em cada chamador.
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
      -- LEFT JOIN nos dois: `updated_by` é nullable e sem FK, e o produto
      -- pode ter sido removido. Linha de auditoria que some porque o alvo
      -- sumiu não é auditoria.
      LEFT JOIN public.products      p  ON p.id  = l.product_id
      LEFT JOIN public.user_accounts ua ON ua.id = l.updated_by
     WHERE l.company_id = p_company_id
       AND (p_product_id IS NULL OR l.product_id = p_product_id)
     -- `now()` é constante na transação: preço e custo alterados no mesmo
     -- UPDATE recebem `last_updated_on` IDÊNTICO. Sem o desempate pelo id a
     -- ordem relativa dessas duas linhas é indefinida, e a tela as
     -- embaralharia entre uma consulta e outra.
     ORDER BY l.last_updated_on DESC, l.id DESC;
END;
$$;
