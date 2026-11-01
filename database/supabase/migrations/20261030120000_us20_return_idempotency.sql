-- US20: contrato obrigatório de idempotência; aplicar junto à adaptação do backend.
-- Depende de 20261030102000_us20_return_guardrails.sql e das etapas US20 anteriores.
-- Não reescreve histórico nem cria enums.
-- Registros anteriores mantêm os três campos NULL; não é possível reconstruir
-- a chave escolhida pelo cliente. O índice UNIQUE admite esses registros legados.
-- ALTER TABLE/UNIQUE exigem locks: programar aplicação conforme volume existente.
-- Rollback operacional preferido: correção incremental. Não remover as chaves
-- de operações já confirmadas nem restaurar escrita sem idempotência em produção.
BEGIN;

ALTER TABLE public.returns
    ADD COLUMN idempotency_key uuid,
    ADD COLUMN request_payload jsonb,
    ADD COLUMN result_payload jsonb,
    ADD CONSTRAINT uq_returns_company_idempotency UNIQUE (company_id, idempotency_key),
    ADD CONSTRAINT ck_returns_idempotency CHECK (
        (idempotency_key IS NULL AND request_payload IS NULL AND result_payload IS NULL)
        OR (idempotency_key IS NOT NULL AND request_payload IS NOT NULL
            AND jsonb_typeof(request_payload) = 'object'
            AND (result_payload IS NULL OR jsonb_typeof(result_payload) = 'object'))
    );

-- Sem CASCADE: dependências inesperadas devem bloquear a migration, não sumir.
-- Remover a assinatura anterior impede contornar a proteção com três argumentos.
DROP FUNCTION public.fn_return_partial_sale(uuid, jsonb, text);

-- US20: devolução parcial ou total, sem emissão fiscal nem liquidação financeira.
-- SECURITY DEFINER: escrita passa pela RPC, não por grants diretos nas tabelas.
CREATE OR REPLACE FUNCTION public.fn_return_partial_sale(
    p_sale_id uuid,
    p_items   jsonb, -- [{"sale_item_id": uuid, "quantity": int}, ...]
    p_reason  text,
    p_idempotency_key uuid
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_actor uuid := public.fn_current_user_id();
    v_company uuid;
    v_status public.sale_status;
    v_reason text := btrim(COALESCE(p_reason, ''));
    v_discount numeric;
    v_sale_total numeric;
    v_original_subtotal numeric;
    v_return_id uuid;
    v_item record;
    v_returned_qty bigint;
    v_returned_amount numeric;
    v_line_net numeric;
    v_amount numeric;
    v_item_discount numeric;
    v_total_amount numeric := 0;
    v_is_total boolean;
    v_request jsonb;
    v_existing_request jsonb;
    v_result jsonb;
BEGIN
    IF v_actor IS NULL THEN
        RAISE EXCEPTION 'Usuário responsável não identificado'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_idempotency_key IS NULL THEN
        RAISE EXCEPTION 'Informe a chave de idempotência UUID'
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_reason !~ '[^[:space:]]' THEN
        RAISE EXCEPTION 'Informe o motivo da devolução'
            USING ERRCODE = 'check_violation';
    END IF;
    -- Separar formato e casts: SQL não garante avaliação da esquerda para a direita.
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' THEN
        RAISE EXCEPTION 'Os itens da devolução devem ser um array JSON'
            USING ERRCODE = 'check_violation';
    END IF;
    IF jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'Informe ao menos um item para devolução'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_items) AS e(item)
         WHERE jsonb_typeof(e.item) <> 'object'
            OR COALESCE(jsonb_typeof(e.item->'sale_item_id'), 'null') <> 'string'
            OR COALESCE(e.item->>'sale_item_id', '') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            OR COALESCE(jsonb_typeof(e.item->'quantity'), 'null') <> 'number'
            OR COALESCE(e.item->>'quantity', '') !~ '^[1-9][0-9]*$'
    ) THEN
        RAISE EXCEPTION 'Item de venda UUID e quantidade inteira positiva são obrigatórios'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_items) AS e(item)
         WHERE (e.item->>'quantity')::numeric > 2147483647
    ) THEN
        RAISE EXCEPTION 'Quantidade acima do limite inteiro permitido'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_items) AS e(item)
         GROUP BY (e.item->>'sale_item_id')::uuid HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Item de venda repetido na mesma devolução'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Canonicaliza UUIDs e ordem; ignora campos extras, como o contrato anterior.
    SELECT jsonb_build_object('sale_id', p_sale_id, 'reason', v_reason, 'items',
        jsonb_agg(jsonb_build_object(
            'sale_item_id', (e.item->>'sale_item_id')::uuid,
            'quantity', (e.item->>'quantity')::integer
        ) ORDER BY (e.item->>'sale_item_id')::uuid))
      INTO v_request FROM jsonb_array_elements(p_items) AS e(item);

    -- Autorizar ANTES de consultar uma resposta anterior, inclusive em retries.
    SELECT s.company_id INTO v_company FROM public.sales s
     WHERE s.id = p_sale_id
       AND public.fn_has_role(s.company_id, ARRAY['ADMIN']::public.user_role[]);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Venda não encontrada ou sem permissão para devolver'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- A unicidade arbitra só empresa/chave. A reserva é revertida junto ao estoque.
    -- Em READ COMMITTED o SELECT seguinte vê o commit vencedor após a espera.
    -- Em snapshots antigos PostgreSQL pode emitir 40001: repetir a transação
    -- inteira com a MESMA chave, nunca gerar outra chave após resultado incerto.
    INSERT INTO public.returns (
        company_id, sale_id, user_id, reason, idempotency_key, request_payload
    ) VALUES (v_company, p_sale_id, v_actor, v_reason, p_idempotency_key, v_request)
    ON CONFLICT ON CONSTRAINT uq_returns_company_idempotency DO NOTHING
    RETURNING id INTO v_return_id;
    IF NOT FOUND THEN
        SELECT r.request_payload, r.result_payload
          INTO v_existing_request, v_result FROM public.returns r
         WHERE r.company_id = v_company AND r.idempotency_key = p_idempotency_key;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Repita a transação com a mesma chave de idempotência'
                USING ERRCODE = 'serialization_failure';
        END IF;
        IF v_existing_request IS DISTINCT FROM v_request THEN
            RAISE EXCEPTION 'Chave de idempotência reutilizada com conteúdo diferente'
                USING ERRCODE = 'PT409';
        END IF;
        IF v_result IS NULL THEN
            RAISE EXCEPTION 'Registro idempotente sem resultado concluído'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN v_result;
    END IF;

    -- Serializa a venda ANTES de consultar devoluções anteriores. A nova versão
    -- MVCC, sem alterar status/valores, também causa serialization_failure se
    -- outra devolução vencer usando snapshot antigo em REPEATABLE READ/SERIALIZABLE.
    -- O trigger de conclusão exige mudança de status e não dispara outra saída.
    UPDATE public.sales AS s SET status = s.status
     WHERE s.id = p_sale_id
       AND public.fn_has_role(s.company_id, ARRAY['ADMIN']::public.user_role[])
     RETURNING s.company_id, s.status, s.discount, s.total
          INTO v_company, v_status, v_discount, v_sale_total;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Venda não encontrada ou sem permissão para devolver'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF v_status <> 'CONCLUIDA' THEN
        RAISE EXCEPTION 'Somente venda concluída pode ser devolvida'
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM si.id FROM public.sale_items si
     WHERE si.sale_id = p_sale_id AND si.company_id = v_company
     ORDER BY si.id FOR UPDATE;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_items) AS e(item)
        LEFT JOIN public.sale_items si ON si.id = (e.item->>'sale_item_id')::uuid
             AND si.sale_id = p_sale_id AND si.company_id = v_company
        LEFT JOIN public.products p ON p.id = si.product_id AND p.company_id = v_company
         WHERE si.id IS NULL OR p.id IS NULL
    ) THEN
        RAISE EXCEPTION 'Item ou produto não encontrado na venda e empresa informadas'
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    -- Produto excluído não pode receber estoque. Produto inativo ainda existente
    -- pode ser restituído; não mudar o estado cadastral dele nesta operação.
    PERFORM p.id FROM public.products p
     WHERE p.company_id = v_company AND p.id IN (
         SELECT si.product_id FROM public.sale_items si
         JOIN jsonb_array_elements(p_items) AS e(item)
           ON si.id = (e.item->>'sale_item_id')::uuid
         WHERE si.sale_id = p_sale_id AND si.company_id = v_company
     ) ORDER BY p.barcode FOR UPDATE;

    SELECT COALESCE(sum(si.quantity::numeric * si.unit_price), 0)
      INTO v_original_subtotal FROM public.sale_items si
     WHERE si.sale_id = p_sale_id AND si.company_id = v_company;
    IF v_original_subtotal::text IN ('NaN', 'Infinity', '-Infinity')
       OR v_discount::text IN ('NaN', 'Infinity', '-Infinity')
       OR v_sale_total::text IN ('NaN', 'Infinity', '-Infinity')
       OR v_discount > v_original_subtotal
       OR v_sale_total <> v_original_subtotal - v_discount THEN
        RAISE EXCEPTION 'Valores originais da venda não conciliam; devolução rejeitada'
            USING ERRCODE = 'check_violation';
    END IF;

    FOR v_item IN
        -- Diferenças de acumulados rateiam centavos sem ultrapassar o desconto.
        -- A janela deve incluir TODOS os itens, não apenas os desta requisição.
        WITH priced AS (
            SELECT si.*, si.quantity::numeric * si.unit_price AS gross,
                   sum(si.quantity::numeric * si.unit_price) OVER (
                       ORDER BY si.id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                   ) AS cumulative_gross
              FROM public.sale_items si
             WHERE si.sale_id = p_sale_id AND si.company_id = v_company
        )
        SELECT priced.*, (e.item->>'quantity')::integer AS requested
          FROM priced JOIN jsonb_array_elements(p_items) AS e(item)
            ON priced.id = (e.item->>'sale_item_id')::uuid
         ORDER BY priced.id
    LOOP
        SELECT COALESCE(sum(ri.quantity), 0), COALESCE(sum(ri.subtotal), 0)
          INTO v_returned_qty, v_returned_amount
          FROM public.return_items ri JOIN public.returns r ON r.id = ri.return_id
         WHERE ri.company_id = v_company AND ri.sale_id = p_sale_id
           AND ri.sale_item_id = v_item.id AND r.status = 'COMPLETED';
        IF v_returned_qty + v_item.requested > v_item.quantity THEN
            RAISE EXCEPTION 'Quantidade excede o disponível para devolução do item % (%)',
                v_item.id, v_item.quantity - v_returned_qty
                USING ERRCODE = 'check_violation';
        END IF;
        IF v_original_subtotal = 0 THEN
            v_line_net := 0;
        ELSE
            v_line_net := v_item.gross - (
                round(v_discount * v_item.cumulative_gross / v_original_subtotal, 2)
                - round(v_discount * (v_item.cumulative_gross - v_item.gross) / v_original_subtotal, 2)
            );
        END IF;
        IF v_returned_amount <> round(v_line_net * v_returned_qty / v_item.quantity, 2) THEN
            RAISE EXCEPTION 'Histórico de valores devolvidos não concilia para o item %', v_item.id
                USING ERRCODE = 'check_violation';
        END IF;
        -- Acumulado por quantidade: devolver 1+1 ou 2 unidades fecha o mesmo valor.
        v_amount := round(v_line_net * (v_returned_qty + v_item.requested) / v_item.quantity, 2)
                    - v_returned_amount;
        v_item_discount := v_item.unit_price * v_item.requested - v_amount;
        INSERT INTO public.return_items (
            company_id, sale_id, return_id, sale_item_id, quantity, unit_price, discount, subtotal
        ) VALUES (
            v_company, p_sale_id, v_return_id, v_item.id, v_item.requested,
            v_item.unit_price, v_item_discount, v_amount
        );
        INSERT INTO public.stock_movements (
            company_id, product_id, sale_id, sale_item_id, return_id, kind,
            quantity, status, note, created_by, confirmed_on
        ) VALUES (
            v_company, v_item.product_id, p_sale_id, v_item.id, v_return_id, 'ENTRADA',
            v_item.requested, 'CONFIRMADA', 'DEVOLUCAO - devolução ' || v_return_id::text,
            v_actor, now()
        );
        v_total_amount := v_total_amount + v_amount;
    END LOOP;

    UPDATE public.returns SET total_amount = v_total_amount, status = 'COMPLETED'
     WHERE id = v_return_id;
    SELECT NOT EXISTS (
        SELECT 1 FROM public.sale_items si
         WHERE si.sale_id = p_sale_id AND si.company_id = v_company
           AND si.quantity > (
               SELECT COALESCE(sum(ri.quantity), 0)
                 FROM public.return_items ri JOIN public.returns r ON r.id = ri.return_id
                WHERE ri.sale_item_id = si.id AND ri.company_id = v_company
                  AND ri.sale_id = p_sale_id AND r.status = 'COMPLETED'
           )
    ) INTO v_is_total;
    -- COMPLETED é a devolução de estoque registrada, NÃO pagamento/NF-e concluídos.
    v_result := jsonb_build_object('return_id', v_return_id, 'status', 'COMPLETED',
                               'total_amount', v_total_amount, 'is_total_return', v_is_total);
    UPDATE public.returns SET result_payload = v_result WHERE id = v_return_id;
    RETURN v_result;
END;
$$;

REVOKE ALL ON FUNCTION public.fn_return_partial_sale(uuid, jsonb, text, uuid)
  FROM PUBLIC, anon, authenticated, app_backend;

GRANT EXECUTE ON FUNCTION public.fn_return_partial_sale(uuid, jsonb, text, uuid)
  TO app_backend, authenticated;

NOTIFY pgrst, 'reload schema';
COMMIT;
