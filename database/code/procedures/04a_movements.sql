-- Registro e confirmação de movimentações. Depende de stock_movements
-- (tables/05) e de fn_has_role (02_authz).
--
-- Vem depois de 04_stock e antes de 05_catalog porque `fn_create_products` e
-- `fn_update_products` passaram a registrar movimentação em vez de escrever
-- `products.stock`.

-- Saldo confirmado de um produto. Uma função, e não a expressão repetida no
-- trigger e na carga inicial: duas cópias da mesma soma divergem, e a
-- divergência aqui significa saldo errado na tela.
-- VOLATILE, e não STABLE: ela é chamada de dentro de um trigger AFTER, onde
-- precisa enxergar a linha que acabou de ser gravada. STABLE amarra a função
-- ao snapshot da consulta chamadora, e um saldo calculado sobre o estado
-- ANTERIOR ficaria errado por uma movimentação a cada vez — erro que só
-- apareceria em produção, somando silenciosamente. O custo é perder inlining
-- numa função que só o trigger e a conferência usam.
CREATE OR REPLACE FUNCTION public.fn_confirmed_balance(p_product_id uuid)
RETURNS integer
LANGUAGE sql VOLATILE
SET search_path = public AS $$
    SELECT COALESCE(SUM(
        CASE m.kind WHEN 'ENTRADA' THEN m.quantity ELSE -m.quantity END
    ), 0)::integer
      FROM public.stock_movements m
     WHERE m.product_id = p_product_id
       AND m.status = 'CONFIRMADA';
$$;

-- Registra uma movimentação. Nasce PENDENTE salvo pedido explícito.
CREATE OR REPLACE FUNCTION public.fn_register_movement(
    p_company_id uuid,
    p_product_id uuid,
    p_kind       public.movement_kind,
    p_quantity   integer,
    p_note       text    DEFAULT NULL,
    p_confirm    boolean DEFAULT false
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
    v_max   integer;
    v_current_stock integer;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para movimentar estoque nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantidade deve ser maior que zero (recebida: %)', p_quantity
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT stock INTO v_current_stock 
      FROM public.products
     WHERE id = p_product_id AND company_id = p_company_id AND active 
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Produto não encontrado ou inativo nesta empresa'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- Se for ENTRADA e for CONFIRMADA na hora, valida o teto máximo
    IF p_kind = 'ENTRADA' AND p_confirm THEN
        v_max := public.fn_get_effective_max_stock(p_product_id);
        IF v_max IS NOT NULL AND (v_current_stock + p_quantity) > v_max THEN
            RAISE EXCEPTION 'Entrada rejeitada: a quantidade (%) somada ao estoque atual (%) ultrapassa o estoque máximo (%)',
                p_quantity, v_current_stock, v_max USING ERRCODE = 'check_violation';
        END IF;
    END IF;





    -- O produto precisa ser DA empresa informada. Sem esta checagem, quem é
    -- STOCK numa empresa movimentaria o estoque de outra.
    PERFORM 1 FROM public.products
     WHERE id = p_product_id AND company_id = p_company_id AND active FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Produto não encontrado ou inativo nesta empresa'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO public.stock_movements
           (company_id, product_id, kind, quantity, status, note,
            created_by, confirmed_on)
    VALUES (p_company_id, p_product_id, p_kind, p_quantity,
            CASE WHEN p_confirm THEN 'CONFIRMADA' ELSE 'PENDENTE' END::public.movement_status,
            p_note, public.fn_current_user_id(),
            CASE WHEN p_confirm THEN now() END)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

-- Confirma uma movimentação pendente. É esta transição que muda o saldo.
CREATE OR REPLACE FUNCTION public.fn_confirm_movement(p_movement_id uuid)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_status  public.movement_status;
    v_product uuid;
BEGIN
    SELECT company_id, product_id INTO v_company, v_product
      FROM public.stock_movements WHERE id = p_movement_id;

    -- Mensagem única para inexistente e sem permissão: não vaza a existência
    -- de movimentações de outra empresa.
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Movimentação não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    PERFORM 1 FROM public.products WHERE id = v_product AND active FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Produto inativo não pode ser movimentado' USING ERRCODE = 'check_violation';
    END IF;
    SELECT status INTO v_status FROM public.stock_movements
     WHERE id = p_movement_id FOR UPDATE;
    IF v_status <> 'PENDENTE' THEN
        RAISE EXCEPTION 'Só movimentação pendente pode ser confirmada (situação atual: %)', v_status
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.stock_movements
       SET status = 'CONFIRMADA', confirmed_on = now()
     WHERE id = p_movement_id;
END;
$$;

-- Cancela. Cancelar uma CONFIRMADA desfaz o efeito dela no saldo, porque o
-- trigger recalcula a soma das que seguem confirmadas.
CREATE OR REPLACE FUNCTION public.fn_cancel_movement(p_movement_id uuid)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_product uuid;
BEGIN
    SELECT company_id, product_id INTO v_company, v_product
      FROM public.stock_movements WHERE id = p_movement_id;

    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Movimentação não encontrada ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    PERFORM 1 FROM public.products WHERE id = v_product FOR UPDATE;
    IF EXISTS (SELECT 1 FROM public.stock_movements
                WHERE id = p_movement_id AND sale_id IS NOT NULL) THEN
        RAISE EXCEPTION 'A saída pertence a uma venda e não pode ser cancelada isoladamente'
            USING ERRCODE = 'check_violation';
    END IF;
    UPDATE public.stock_movements
       SET status = 'CANCELADA'
     WHERE id = p_movement_id;
END;
$$;

-- Edição de estoque pelo código de barras (US09).
--
-- É um ATALHO sobre fn_register_movement, não um caminho paralelo: escrever
-- `products.stock` aqui seria desfeito pelo recálculo do trigger de
-- triggers/04 na movimentação seguinte, e o saldo passaria a depender de qual
-- caminho foi usado por último.
--
-- Não recebe o usuário por parâmetro de propósito: a autoria sai de
-- fn_current_user_id(), como em todo o resto desta árvore. Recebê-lo deixaria
-- o chamador registrar a alteração em nome de outra pessoa.
--
-- `p_company_id` é obrigatório porque barcode só é único DENTRO da empresa
-- (UNIQUE (company_id, barcode) em tables/03_catalog.sql).
CREATE OR REPLACE FUNCTION public.fn_edit_product_stock(
    p_company_id uuid,
    p_barcode    text,
    p_quantity   integer,
    p_note       text DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_product_id uuid;
    v_movement   uuid;
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantidade deve ser maior que zero (recebida: %)', p_quantity
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT id INTO v_product_id
      FROM public.products
     WHERE company_id = p_company_id AND barcode = p_barcode AND active;
    IF v_product_id IS NULL THEN
        RAISE EXCEPTION 'Produto não encontrado ou inativo nesta empresa: %', p_barcode
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- A permissão (ADMIN/STOCK) e o vínculo produto-empresa são conferidos
    -- aqui dentro; repetir a checagem antes seria uma segunda regra para
    -- manter em dia.
    v_movement := public.fn_register_movement(
        p_company_id, v_product_id, 'ENTRADA', p_quantity,
        COALESCE(p_note, 'Entrada manual de estoque'), true);

    UPDATE public.products
       SET last_updated_by = public.fn_current_user_id()
     WHERE id = v_product_id;

    RETURN v_movement;
END;
$$;

-- Ajuste manual de inventário (H11).
--
-- O operador informa o saldo CONTADO e a função deriva o lançamento. Não é um
-- caminho paralelo ao saldo: grava uma movimentação comum já CONFIRMADA e
-- deixa o trigger de triggers/04 recalcular `products.stock`, como todo o
-- resto. Escrever o saldo aqui seria desfeito pela movimentação seguinte.
--
-- ATÔMICA de propósito, sem o par registrar/confirmar das irmãs: contagem é
-- uma afirmação sobre AGORA. Um ajuste pendente confirmado meia hora depois
-- aplicaria uma diferença calculada sobre um saldo que já mudou.
CREATE OR REPLACE FUNCTION public.fn_register_adjustment(
    p_company_id       uuid,
    p_product_id       uuid,
    p_counted_balance  integer,
    p_expected_balance integer,
    p_reason           public.adjustment_reason,
    p_detail           text DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_current integer;
    v_kind    public.movement_kind;
    v_qty     integer;
    v_detail  text := nullif(btrim(coalesce(p_detail, '')), '');
    v_id      uuid;
    v_final   integer;
    v_max     integer;
BEGIN
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para ajustar o estoque nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF p_counted_balance IS NULL OR p_counted_balance < 0 THEN
        RAISE EXCEPTION 'O saldo contado não pode ser negativo (recebido: %)',
            p_counted_balance USING ERRCODE = 'check_violation';
    END IF;

    IF p_reason IS NULL THEN
        RAISE EXCEPTION 'Informe o motivo do ajuste'
            USING ERRCODE = 'check_violation';
    END IF;

    v_max := public.fn_get_effective_max_stock(p_product_id);

    IF v_max IS NOT NULL AND p_counted_balance > v_max THEN
        RAISE EXCEPTION 'O saldo contado (%) ultrapassa o estoque máximo permitido (%) para este produto',
        p_counted_balance, v_max USING ERRCODE = 'check_violation';
    END IF;

    IF p_reason = 'OUTRO' AND v_detail IS NULL THEN
        RAISE EXCEPTION 'O motivo "Outro" exige uma justificativa escrita'
            USING ERRCODE = 'check_violation';
    END IF;

    -- FOR UPDATE trava a linha do produto até o fim da transação: dois
    -- ajustes simultâneos do mesmo item serializam aqui, em vez de
    -- calcularem a diferença sobre o mesmo saldo e um sobrescrever o outro.
    SELECT stock INTO v_current
      FROM public.products
     WHERE id = p_product_id AND company_id = p_company_id AND active
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Produto não encontrado ou inativo nesta empresa'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- O saldo que a TELA exibiu faz parte do pedido. Recalcular em silêncio
    -- sobre um saldo que mudou daria um número que não é o contado nem o
    -- correto: se alguém confirmou uma entrada e pôs a mercadoria na
    -- prateleira, só uma recontagem resolve.
    IF p_expected_balance IS NOT NULL AND p_expected_balance <> v_current THEN
        RAISE EXCEPTION 'O saldo mudou desde a contagem (na tela: %, agora: %)',
            p_expected_balance, v_current USING ERRCODE = 'serialization_failure';
    END IF;

    IF p_counted_balance = v_current THEN
        RAISE EXCEPTION 'O saldo contado é igual ao saldo atual (%)', v_current
            USING ERRCODE = 'check_violation';
    END IF;

    IF p_counted_balance > v_current THEN
        v_kind := 'ENTRADA';
        v_qty  := p_counted_balance - v_current;
    ELSE
        v_kind := 'SAIDA';
        v_qty  := v_current - p_counted_balance;
    END IF;

    INSERT INTO public.stock_movements
           (company_id, product_id, kind, quantity, status, note,
            adjustment_reason, counted_balance, created_by, confirmed_on)
    VALUES (p_company_id, p_product_id, v_kind, v_qty, 'CONFIRMADA', v_detail,
            p_reason, p_counted_balance, public.fn_current_user_id(), now())
    RETURNING id INTO v_id;

    UPDATE public.products
       SET last_updated_by = public.fn_current_user_id()
     WHERE id = p_product_id;

    -- O trigger AFTER INSERT já recalculou products.stock quando o INSERT
    -- acima terminou. Reler e conferir é o que transforma "o saldo
    -- resultante" de expectativa em garantia: ou é o contado, ou a
    -- transação inteira volta atrás.
    SELECT stock INTO v_final FROM public.products WHERE id = p_product_id;
    IF v_final <> p_counted_balance THEN
        RAISE EXCEPTION 'Saldo resultante (%) diferente do contado (%); ajuste desfeito',
            v_final, p_counted_balance USING ERRCODE = 'check_violation';
    END IF;

    RETURN v_id;
END;
$$;
