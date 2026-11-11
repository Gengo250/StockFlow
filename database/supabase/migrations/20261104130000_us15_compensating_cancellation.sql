-- US15: entradas compensatórias, sem anular saídas nem inferir vínculos.
-- Incremental: requer 20261104120000_us15_cancel_pending_validation.sql.
-- Não é um script de reinstalação idempotente. Nenhum UPDATE/backfill de dados.
-- cancellation_id permanece NULL no histórico. Cancelamentos anteriores já
-- restituídos pelo mecanismo legado não recebem novas entradas.
-- Restituição sujeita ao estoque máximo pelos triggers existentes.
-- O FK de escopo revalida vínculos de item já preenchidos: inconsistência
-- impede a migration, em vez de corrigir ou inferir a origem silenciosamente.
-- Rollback operacional: suspender cancelamentos e usar migration corretiva;
-- nunca apagar auditoria/entradas nem restaurar a anulação legada em produção
-- sem avaliar os cancelamentos compensatórios já confirmados.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.stock_movements sm
        WHERE sm.sale_id IS NOT NULL AND sm.sale_item_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM public.sale_items i
               WHERE i.company_id = sm.company_id AND i.sale_id = sm.sale_id
                 AND i.id = sm.sale_item_id
          )
    ) THEN
        RAISE EXCEPTION 'Inconsistência nos vínculos de item de stock_movements; migration US15 recusada sem backfill'
            USING ERRCODE = 'check_violation';
    END IF;
END;
$$;

ALTER TABLE public.sale_reversals
    ADD CONSTRAINT uq_sale_reversals_company_sale_id UNIQUE (company_id, sale_id, id);

ALTER TABLE public.stock_movements
    ADD COLUMN cancellation_id uuid,
    ADD CONSTRAINT fk_stock_movements_cancellation
        FOREIGN KEY (company_id, sale_id, cancellation_id)
        REFERENCES public.sale_reversals (company_id, sale_id, id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_stock_movements_sale_item_scope
        FOREIGN KEY (company_id, sale_id, sale_item_id)
        REFERENCES public.sale_items (company_id, sale_id, id) ON DELETE RESTRICT,
    ADD CONSTRAINT ck_stock_movements_cancellation CHECK (
        cancellation_id IS NULL OR (
            sale_id IS NOT NULL AND sale_item_id IS NOT NULL
            AND kind = 'ENTRADA' AND status = 'CONFIRMADA'
            AND created_by IS NOT NULL AND confirmed_on IS NOT NULL
            AND adjustment_reason IS NULL AND counted_balance IS NULL
        )
    );
CREATE UNIQUE INDEX uq_stock_movements_cancellation_item
    ON public.stock_movements (cancellation_id, sale_item_id)
    WHERE cancellation_id IS NOT NULL;

-- Uma entrada não pode ser, ao mesmo tempo, cancelamento US15 e devolução US20.
ALTER TABLE public.stock_movements DROP CONSTRAINT ck_stock_movements_return;
ALTER TABLE public.stock_movements ADD CONSTRAINT ck_stock_movements_return CHECK (
    return_id IS NULL OR (
        sale_id IS NOT NULL AND sale_item_id IS NOT NULL
        AND cancellation_id IS NULL
        AND kind = 'ENTRADA' AND status = 'CONFIRMADA'
        AND created_by IS NOT NULL AND confirmed_on IS NOT NULL
        AND adjustment_reason IS NULL AND counted_balance IS NULL
    )
);

CREATE OR REPLACE FUNCTION public.fn_process_sale_completion()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_item    RECORD;
    v_balance integer;
BEGIN
    IF OLD.status <> 'PENDENTE' THEN
        RAISE EXCEPTION 'Somente venda pendente pode ser concluída'
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM i.id FROM public.sale_items i
     WHERE i.sale_id = NEW.id ORDER BY i.id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Venda sem itens; conclusão recusada'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.sale_items i
        LEFT JOIN public.products p
          ON p.id = i.product_id AND p.company_id = NEW.company_id
        WHERE i.sale_id = NEW.id
          AND (i.company_id <> NEW.company_id OR p.id IS NULL)
    ) OR EXISTS (
        SELECT 1 FROM public.stock_movements sm
         WHERE sm.sale_id = NEW.id AND sm.status = 'CONFIRMADA'
    ) THEN
        RAISE EXCEPTION 'Inconsistência nos itens ou movimentações da venda; conclusão recusada'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Também protege transições diretas: não depender só dos locks do checkout.
    PERFORM p.id FROM public.products p
     WHERE p.company_id = NEW.company_id
       AND p.id IN (SELECT i.product_id FROM public.sale_items i WHERE i.sale_id = NEW.id)
     ORDER BY p.barcode FOR UPDATE;

    INSERT INTO public.sales_log (company_id, sale_id, created_by)
    VALUES (NEW.company_id, NEW.id, NEW.created_by);

    FOR v_item IN
        SELECT i.id, i.product_id, i.product_name, i.quantity
          FROM public.sale_items i
          JOIN public.products p ON p.id = i.product_id AND p.company_id = i.company_id
         WHERE i.sale_id = NEW.id AND i.company_id = NEW.company_id
         ORDER BY p.barcode, i.id
    LOOP
        -- Conferência explícita antes de inserir. Sem ela a falta de estoque
        -- apareceria como violação do CHECK `stock >= 0` de products, com
        -- mensagem que não diz qual produto faltou.
        v_balance := public.fn_confirmed_balance(v_item.product_id);
        IF v_balance < v_item.quantity THEN
            RAISE EXCEPTION
                'Estoque insuficiente para % (disponível: %, vendido: %)',
                v_item.product_name, v_balance, v_item.quantity
                USING ERRCODE = 'check_violation';
        END IF;

        INSERT INTO public.stock_movements (
            company_id, product_id, sale_id, sale_item_id, kind, quantity, status,
            note, created_by, confirmed_on
        ) VALUES (
            NEW.company_id, v_item.product_id, NEW.id, v_item.id, 'SAIDA',
            v_item.quantity, 'CONFIRMADA',
            'SAIDA_VENDA - venda ' || NEW.id::text, NEW.created_by, now()
        );
    END LOOP;

    RETURN NULL;
END;
$$;

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
    v_cancellation uuid;
    v_item record;
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

    -- Falhar antes de registrar a auditoria ou tocar no estoque. A guarda do
    -- UPDATE final permanece como defesa adicional. A US20 serializa sales.
    IF EXISTS (
        SELECT 1 FROM public.returns r
         WHERE r.sale_id = p_sale_id AND r.status = 'COMPLETED'
    ) THEN
        RAISE EXCEPTION 'Venda com devolução registrada; cancelamento não permitido'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM public.sale_reversals r WHERE r.sale_id = p_sale_id) THEN
        RAISE EXCEPTION 'Inconsistência: venda já possui reversão registrada'
            USING ERRCODE = 'check_violation';
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
        PERFORM i.id FROM public.sale_items i
         WHERE i.sale_id = p_sale_id ORDER BY i.id FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Inconsistência: venda concluída sem itens; cancelamento recusado'
                USING ERRCODE = 'check_violation';
        END IF;

        -- Mesma ordem do checkout e da US20: código de barras ascendente.
        PERFORM p.id
          FROM public.products p
         WHERE p.company_id = v_company
           AND p.id IN (
                SELECT i.product_id FROM public.sale_items i
                 WHERE i.sale_id = p_sale_id AND i.company_id = v_company
            )
          ORDER BY p.barcode FOR UPDATE;

        PERFORM sm.id FROM public.stock_movements sm
         WHERE sm.sale_id = p_sale_id ORDER BY sm.id FOR UPDATE;

        -- Uma saída identificada por item, integral e ainda confirmada. Não
        -- aceitar movimento extra, cancelado, sem item ou de outra origem.
        -- Produto inativo pode voltar; produto ausente ou de outra empresa não.
        IF EXISTS (
            SELECT 1 FROM public.sale_items i
            LEFT JOIN public.products p
              ON p.id = i.product_id AND p.company_id = v_company
            WHERE i.sale_id = p_sale_id
              AND (i.company_id <> v_company OR p.id IS NULL OR (
                  SELECT count(*) FROM public.stock_movements sm
                   WHERE sm.sale_id = p_sale_id AND sm.sale_item_id = i.id
              ) <> 1)
        ) OR EXISTS (
            SELECT 1 FROM public.stock_movements sm
            LEFT JOIN public.sale_items i
              ON i.id = sm.sale_item_id AND i.sale_id = p_sale_id
             AND i.company_id = v_company
            WHERE sm.sale_id = p_sale_id
              AND (i.id IS NULL OR sm.company_id <> v_company
                   OR sm.product_id IS DISTINCT FROM i.product_id
                   OR sm.quantity <> i.quantity
                   OR sm.kind <> 'SAIDA' OR sm.status <> 'CONFIRMADA'
                   OR sm.confirmed_on IS NULL
                   OR sm.return_id IS NOT NULL OR sm.cancellation_id IS NOT NULL
                   OR sm.adjustment_reason IS NOT NULL OR sm.counted_balance IS NOT NULL)
        ) THEN
            RAISE EXCEPTION 'Inconsistência entre itens e saídas confirmadas da venda; cancelamento recusado sem inferir vínculos'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    -- O UNIQUE (sale_id) desta tabela é o que torna a reversão terminal; a
    -- conferência de status acima é a mensagem amigável para o caso comum.
    INSERT INTO public.sale_reversals (company_id, sale_id, kind, reason, created_by)
    VALUES (v_company, p_sale_id, 'CANCELAMENTO', v_reason, v_actor)
    RETURNING id INTO v_cancellation;

    IF v_status = 'CONCLUIDA' THEN
        FOR v_item IN
            SELECT i.id, i.product_id, i.quantity
              FROM public.sale_items i
              JOIN public.products p ON p.id = i.product_id AND p.company_id = i.company_id
             WHERE i.sale_id = p_sale_id AND i.company_id = v_company
             ORDER BY p.barcode, i.id
        LOOP
            INSERT INTO public.stock_movements (
                company_id, product_id, sale_id, sale_item_id, cancellation_id,
                kind, quantity, status, note, created_by, confirmed_on
            ) VALUES (
                v_company, v_item.product_id, p_sale_id, v_item.id, v_cancellation,
                'ENTRADA', v_item.quantity, 'CONFIRMADA',
                'CANCELAMENTO_VENDA - cancelamento ' || v_cancellation::text, v_actor, now()
            );
        END LOOP;
    END IF;

    -- Os triggers existentes continuam validando caixa e devoluções. Uma
    -- recusa neste UPDATE reverte também a auditoria e todas as entradas.
    UPDATE public.sales SET status = 'CANCELADA' WHERE id = p_sale_id;

    RETURN jsonb_build_object('sale_id', p_sale_id, 'kind', 'CANCELAMENTO',
                              'reason', v_reason, 'status', 'CANCELADA');
END;
$$;

-- Trigger não é uma RPC. Mantém a superfície de cancelamento e corrige o
-- desalinhamento das duas RPCs US20 entre schema declarativo e migrations.
REVOKE ALL ON FUNCTION public.fn_process_sale_completion()
    FROM PUBLIC, anon, authenticated, app_backend;
REVOKE ALL ON FUNCTION public.fn_cancel_sale(uuid, text),
                           public.fn_return_partial_sale(uuid, jsonb, text, uuid),
                           public.fn_get_returnable_items(uuid)
    FROM PUBLIC, anon, authenticated, app_backend;
GRANT EXECUTE ON FUNCTION public.fn_cancel_sale(uuid, text),
                          public.fn_return_partial_sale(uuid, jsonb, text, uuid),
                          public.fn_get_returnable_items(uuid)
    TO app_backend, authenticated;

COMMIT;
