-- US17: consulta do histórico de vendas, cancelamento e devolução.
--
-- Sem BEGIN/COMMIT próprios: `ALTER TYPE ... ADD VALUE` convive mal com
-- transação explícita, e nenhum comando aqui exige uma. Mesmo caminho de
-- 20261013140000, que já acrescentou 'CANCELADA' a este enum.
--
-- O remoto já tem `sale_status` com três rótulos, então aqui é ALTER e não
-- CREATE. A fonte declarativa (database/code) descreve o estado final, com
-- os quatro rótulos, porque ela é aplicada em banco limpo.

ALTER TYPE public.sale_status ADD VALUE IF NOT EXISTS 'DEVOLVIDA';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
          JOIN pg_namespace n ON n.oid = t.typnamespace
         WHERE n.nspname = 'public' AND t.typname = 'sale_reversal_kind'
    ) THEN
        CREATE TYPE public.sale_reversal_kind AS ENUM ('CANCELAMENTO', 'DEVOLUCAO');
    END IF;
END $$;

-- Vínculo entre a venda original e a operação que a desfez. Tabela, e não
-- colunas em `sales`: o vínculo tem autor, motivo e instante próprios.
CREATE TABLE IF NOT EXISTS public.sale_reversals (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL,
    sale_id     uuid NOT NULL,
    kind        public.sale_reversal_kind NOT NULL,
    reason      text NOT NULL CHECK (btrim(reason) <> ''),
    created_by  uuid,
    created_on  timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE CASCADE,
    -- Reversão é TERMINAL: venda revertida não acumula reversão.
    UNIQUE (sale_id)
);
CREATE INDEX IF NOT EXISTS idx_sale_reversals_company
    ON public.sale_reversals (company_id);

ALTER TABLE public.sale_reversals ENABLE ROW LEVEL SECURITY;

-- SELECT e nada mais, como `sales`: a escrita é exclusiva das funções
-- SECURITY DEFINER desta mesma migration.
GRANT SELECT ON public.sale_reversals TO app_backend, authenticated;

DROP POLICY IF EXISTS sale_reversals_select ON public.sale_reversals;
CREATE POLICY sale_reversals_select ON public.sale_reversals
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

-- ------------------------------------------- histórico de vendas (US17)
--
-- Consulta paginada, filtrável e ordenável. Concentrada numa função, e não
-- montada no cliente, por dois motivos: `max_rows` do PostgREST corta a
-- listagem em 1000 linhas sem avisar, e dois adaptadores (Supabase e
-- demonstração) montando filtro cada um do seu jeito divergem em silêncio.
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
SET search_path = public AS $$
-- Os nomes de RETURNS TABLE viram variáveis e competem com os nomes de
-- coluna. Toda referência abaixo é qualificada, e esta diretiva é a rede
-- para a próxima linha que alguém acrescentar sem qualificar.
#variable_conflict use_column
BEGIN
    -- SECURITY DEFINER passa por cima da RLS, então a checagem que
    -- `sales_select` faz na tabela precisa ser repetida aqui. Sem ela, esta
    -- função vira a porta dos fundos do próprio histórico.
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Sem permissão para consultar o histórico desta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- Página sem teto é `list_all` com outro nome, e devolveria ao cliente
    -- exatamente o volume que a paginação existe para evitar.
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
           -- Casa por PREFIXO: é como a tela mostra o identificador, e
           -- digitar o uuid inteiro para achar uma venda não é consulta.
           AND (p_sale_id   IS NULL OR s.id::text LIKE lower(btrim(p_sale_id)) || '%')
           AND (p_from      IS NULL OR s.created_on >= p_from)
           -- Limite superior EXCLUSIVO: o chamador manda o início do dia
           -- seguinte, e assim o último dia do período entra inteiro.
           AND (p_to        IS NULL OR s.created_on < p_to)
           AND (p_client_id IS NULL OR s.client_id = p_client_id)
           AND (p_seller_id IS NULL OR s.created_by = p_seller_id)
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
           -- Calculado ANTES do LIMIT: é o total que casa com o filtro, que
           -- é o que a tela precisa para saber quantas páginas existem. Uma
           -- segunda consulta de contagem poderia divergir desta sob
           -- concorrência, e a tela prometeria página que não existe.
           count(*) OVER ()
      FROM filtradas f
      -- LEFT JOIN nos três: a venda pode não ter reversão, e conta removida
      -- não pode apagar a linha do histórico.
      LEFT JOIN public.sale_reversals r   ON r.sale_id = f.id
      LEFT JOIN public.user_accounts  ua  ON ua.id = f.created_by
      LEFT JOIN public.user_accounts  rua ON rua.id = r.created_by
     ORDER BY
        CASE WHEN p_sort = 'DATA_DESC'   THEN f.created_on END DESC,
        CASE WHEN p_sort = 'DATA_ASC'    THEN f.created_on END ASC,
        CASE WHEN p_sort = 'VALOR_DESC'  THEN f.total      END DESC,
        CASE WHEN p_sort = 'VALOR_ASC'   THEN f.total      END ASC,
        CASE WHEN p_sort = 'CLIENTE_ASC' THEN lower(f.client_name) END ASC,
        -- Desempate obrigatório: duas vendas no mesmo instante têm ordem
        -- indefinida sem ele, e a página 2 repetiria ou pularia linha.
        f.id DESC
     LIMIT p_limit OFFSET p_offset;
END;
$$;

GRANT EXECUTE ON FUNCTION public.fn_list_sales(
    uuid, text, timestamptz, timestamptz, uuid, uuid,
    public.sale_status, text, integer, integer
) TO app_backend, authenticated;

-- Cancelamento de venda (US17).
--
-- A venda não deveria ter existido: as saídas dela passam a CANCELADA e o
-- trigger de recálculo devolve o saldo. É o mesmo contrato de
-- `fn_cancel_movement` -- "cancelar uma confirmada devolve o saldo" -- e a
-- guarda de `trg_protect_confirmed_movement` aceita essa transição de
-- propósito, porque só o status muda.
--
-- Nasce aqui, e não em `fn_cancel_movement`, porque aquela recusa cancelar
-- saída vinculada a venda: desfazer meia venda não é operação legítima.
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
    -- A empresa sai da LINHA, nunca de parâmetro do chamador: é o padrão
    -- que `fn_update_products` estabeleceu nesta árvore.
    SELECT s.company_id, s.status INTO v_company, v_status
      FROM public.sales s WHERE s.id = p_sale_id FOR UPDATE;

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

    IF v_status <> 'CONCLUIDA' THEN
        RAISE EXCEPTION
            'Somente venda concluída pode ser cancelada (situação atual: %)',
            v_status USING ERRCODE = 'check_violation';
    END IF;

    -- O UNIQUE (sale_id) desta tabela é o que torna a reversão terminal; a
    -- conferência de status acima é a mensagem amigável para o caso comum.
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

-- Devolução de venda (US17).
--
-- A venda ACONTECEU e a mercadoria voltou: a saída original continua
-- confirmada e uma ENTRADA compensatória por item devolve o saldo. Anular a
-- saída aqui apagaria do histórico de estoque que houve venda, que é
-- justamente o que distingue devolução de cancelamento.
--
-- Devolução é sempre TOTAL nesta história. A parcial exigiria itens
-- devolvidos, recálculo do total efetivo e um estado intermediário.
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

    INSERT INTO public.sale_reversals (company_id, sale_id, kind, reason, created_by)
    VALUES (v_company, p_sale_id, 'DEVOLUCAO', v_reason, v_actor);

    FOR v_item IN
        SELECT i.product_id, i.quantity
          FROM public.sale_items i
         WHERE i.sale_id = p_sale_id AND i.product_id IS NOT NULL
         -- Mesma ordem de bloqueio da conclusão da venda (triggers/06), para
         -- que duas operações concorrentes sobre os mesmos produtos não se
         -- cruzem em sentidos opostos.
         ORDER BY i.product_id, i.id
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

GRANT EXECUTE ON FUNCTION public.fn_cancel_sale(uuid, text) TO app_backend, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_return_sale(uuid, text) TO app_backend, authenticated;
