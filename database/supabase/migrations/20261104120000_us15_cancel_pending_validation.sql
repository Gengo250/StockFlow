-- US15, tarefa 1: autorização, justificativa e cancelamento de pendência.
-- Sem backfill, novos enums ou alteração de assinatura/retorno da RPC.
-- PENDENTE não movimenta estoque; CONCLUIDA mantém a reversão legada.
-- Entradas compensatórias serão tratadas em tarefa posterior.
-- Preserva os triggers de caixa e de proteção após devolução.
-- Rollback: preferir migration corretiva da função, sem apagar auditoria.
BEGIN;

CREATE OR REPLACE FUNCTION public.fn_cancel_sale(
    p_sale_id uuid,
    p_reason  text
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_company uuid;
    v_status  public.sale_status;
    v_actor   uuid := public.fn_current_user_id();
    v_reason  text := regexp_replace(
        COALESCE(p_reason, ''), '^[[:space:]]+|[[:space:]]+$', '', 'g'
    );
BEGIN
    IF v_actor IS NULL THEN
        RAISE EXCEPTION 'Usuário responsável não identificado'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- A empresa sai da LINHA, nunca de parâmetro do chamador: é o padrão
    -- que `fn_update_products` estabeleceu nesta árvore.
    -- Filtrar autorização antes de adquirir o bloqueio evita que um usuário
    -- sem alçada bloqueie uma venda de outra empresa ou de outro perfil.
    SELECT s.company_id, s.status INTO v_company, v_status
      FROM public.sales s
     WHERE s.id = p_sale_id
       AND public.fn_has_role(s.company_id, ARRAY['ADMIN']::public.user_role[])
     FOR UPDATE;

    -- Venda inexistente e venda de outra empresa dão a MESMA recusa: separar
    -- as duas contaria ao chamador que o identificador existe.
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Venda não encontrada ou sem permissão para cancelar'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF v_reason = '' THEN
        RAISE EXCEPTION 'Informe o motivo do cancelamento'
            USING ERRCODE = 'check_violation';
    END IF;
    IF char_length(v_reason) > 300 THEN
        RAISE EXCEPTION 'O motivo deve ter no máximo 300 caracteres'
            USING ERRCODE = 'check_violation';
    END IF;

    IF v_status IS NULL OR v_status NOT IN ('PENDENTE', 'CONCLUIDA') THEN
        RAISE EXCEPTION
            'Somente venda pendente ou concluída pode ser cancelada (situação atual: %)',
            v_status USING ERRCODE = 'check_violation';
    END IF;

    IF v_status = 'PENDENTE' THEN
        -- Não corrigir silenciosamente uma pendência com estoque já afetado.
        -- Só leitura: nenhum movimento ou saldo é alterado neste caminho.
        IF EXISTS (
            SELECT 1 FROM public.stock_movements sm
             WHERE sm.sale_id = p_sale_id AND sm.status = 'CONFIRMADA'
        ) THEN
            RAISE EXCEPTION 'Venda pendente possui movimentação confirmada; revise a inconsistência antes de cancelar'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        -- Mesma ordem do checkout e da US20: código de barras ascendente.
        PERFORM p.id
          FROM public.products p
         WHERE p.company_id = v_company
           AND p.id IN (
                SELECT sm.product_id FROM public.stock_movements sm
                 WHERE sm.sale_id = p_sale_id AND sm.status = 'CONFIRMADA'
                   AND sm.product_id IS NOT NULL
            )
          ORDER BY p.barcode FOR UPDATE;
    END IF;

    -- O UNIQUE (sale_id) desta tabela é o que torna a reversão terminal; a
    -- conferência de status acima é a mensagem amigável para o caso comum.
    INSERT INTO public.sale_reversals (company_id, sale_id, kind, reason, created_by)
    VALUES (v_company, p_sale_id, 'CANCELAMENTO', v_reason, v_actor);

    IF v_status = 'CONCLUIDA' THEN
        UPDATE public.stock_movements
           SET status = 'CANCELADA'
         WHERE sale_id = p_sale_id AND status = 'CONFIRMADA';
    END IF;

    -- Os triggers existentes continuam validando caixa e devoluções. Uma
    -- recusa neste UPDATE reverte também a auditoria e a reversão acima.
    UPDATE public.sales SET status = 'CANCELADA' WHERE id = p_sale_id;

    RETURN jsonb_build_object('sale_id', p_sale_id, 'kind', 'CANCELAMENTO',
                              'reason', v_reason, 'status', 'CANCELADA');
END;
$$;

REVOKE ALL ON FUNCTION public.fn_cancel_sale(uuid, text)
    FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_cancel_sale(uuid, text)
    TO app_backend, authenticated;

COMMIT;
