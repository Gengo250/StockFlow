-- Estoque mínimo e painel. fn_stock_state precisa existir antes da view
-- vw_stock_situation, que a chama.

-- A ORDEM das cláusulas é a regra, não um detalhe de escrita.
--
-- Mínimo ausente e mínimo zero deixaram de ser a mesma coisa: ausente
-- significa "ninguém configurou" e nunca alerta, nem com saldo negativo;
-- zero é uma decisão explícita de só alertar quando acabar. Por isso o
-- teste de NULL vem antes do teste de saldo, e o de saldo antes do de
-- mínimo zero.
--
-- A terceira cláusula não é redundante com o ELSE: `p_min = 0` torna
-- `p_min * 1.2` igual a zero, então saldo 5 com mínimo 0 não é `<= 0`,
-- não é `<= p_min` e não é `< 0` — cairia no ELSE por acidente, e um dia
-- alguém mexeria no ELSE sem perceber que ele carregava esse caso.
CREATE OR REPLACE FUNCTION public.fn_stock_state(
    p_stock integer,
    p_min   integer
) RETURNS public.stock_state
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_min IS NULL             THEN 'NORMAL'::public.stock_state
        WHEN COALESCE(p_stock, 0) <= 0 THEN 'CRITICO'::public.stock_state
        WHEN p_min = 0                 THEN 'NORMAL'::public.stock_state
        WHEN p_stock <= p_min          THEN 'BAIXO'::public.stock_state
        WHEN p_stock <  p_min * 1.2    THEN 'ATENCAO'::public.stock_state
        ELSE                                'NORMAL'::public.stock_state
    END;
$$;

CREATE OR REPLACE FUNCTION public.fn_set_max_stock(
    p_product_id uuid,
    p_max        integer
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
    v_min integer;
    v_global_limit integer;
    v_current_stock integer;
BEGIN
    --  Validação de valor negativo
    IF p_max < 0 THEN
        RAISE EXCEPTION 'Estoque máximo não pode ser negativo (recebido: %)', p_max
            USING ERRCODE = 'check_violation';
    END IF;
    --  Verifica empresa e papel
    SELECT company_id INTO v_company FROM public.products WHERE id = p_product_id;
    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Produto não encontrado ou sem permissão'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    --Teto global (ou per‑company) -------------------------------------------------
    SELECT max_stock_limit INTO v_global_limit FROM public.company WHERE id = v_company;
    IF v_global_limit IS NOT NULL AND p_max > v_global_limit THEN
        RAISE EXCEPTION 'O estoque máximo (%) excede o teto da empresa (%)',
            p_max, v_global_limit USING ERRCODE = 'check_violation';
    END IF;
    -- Validação contra o estoque  mínimo
    SELECT min_quantity INTO v_min FROM public.product_stock WHERE product_id = p_product_id;
    IF p_max IS NOT NULL AND v_min IS NOT NULL AND p_max < v_min THEN
        RAISE EXCEPTION 'Estoque máximo (%s) não pode ser inferior ao mínimo (%s)',
            p_max, v_min USING ERRCODE = 'check_violation';
    END IF;
    -- Não pode ser menor que o saldo físico 
    SELECT stock INTO v_current_stock FROM public.products WHERE id = p_product_id;
    IF p_max IS NOT NULL AND v_current_stock > p_max THEN
        RAISE EXCEPTION 'Estoque máximo (%) não pode ser menor que o saldo atual (%)',
            p_max, v_current_stock USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.product_stock (product_id, max_quantity, updated_on)
    VALUES (p_product_id, p_max, now())
    ON CONFLICT (product_id) DO UPDATE
       SET max_quantity = EXCLUDED.max_quantity,
           updated_on   = now();
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_set_min_stock(
    p_product_id uuid,
    p_min        integer
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
BEGIN
    IF p_min IS NULL THEN
        RAISE EXCEPTION 'Estoque mínimo é obrigatório' USING ERRCODE = 'not_null_violation';
    END IF;
    IF p_min < 0 THEN
        RAISE EXCEPTION 'Estoque mínimo não pode ser negativo (recebido: %)', p_min
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT company_id INTO v_company FROM public.products WHERE id = p_product_id;

    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Produto não encontrado ou sem permissão' USING ERRCODE = 'insufficient_privilege';
    END IF;

    INSERT INTO public.product_stock (product_id, min_quantity)
    VALUES (p_product_id, p_min)
    ON CONFLICT (product_id)
    DO UPDATE SET min_quantity = EXCLUDED.min_quantity;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_set_min_stock_batch(p_items jsonb)
RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_item jsonb;
    v_n    integer := 0;
BEGIN
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' THEN
        RAISE EXCEPTION 'p_items deve ser um array JSON' USING ERRCODE = 'invalid_parameter_value';
    END IF;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        PERFORM public.fn_set_min_stock((v_item->>'product_id')::uuid, (v_item->>'min')::int);
        v_n := v_n + 1;
    END LOOP;

    RETURN v_n;
END;
$$;

-- As duas abaixo leem vw_stock_situation, criada depois. São plpgsql, cujo
-- corpo não é validado na criação, então a ordem aqui é segura.
CREATE OR REPLACE FUNCTION public.fn_company_stock_state(p_company_id uuid)
RETURNS public.company_stock_state
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_total     int;
    v_critico   int;
    v_baixo     int;
    v_atencao   int;
    v_pct_baixo numeric;
BEGIN
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Sem acesso a esta empresa' USING ERRCODE = 'insufficient_privilege';
    END IF;

    SELECT COUNT(*),
           COUNT(*) FILTER (WHERE state = 'CRITICO'),
           COUNT(*) FILTER (WHERE state = 'BAIXO'),
           COUNT(*) FILTER (WHERE state = 'ATENCAO')
      INTO v_total, v_critico, v_baixo, v_atencao
      FROM public.vw_stock_situation
     WHERE company_id = p_company_id;

    IF v_total = 0 THEN
        RETURN 'SEGURO';
    END IF;

    v_pct_baixo := (v_baixo::numeric / v_total) * 100;

    IF v_critico > 0 THEN
        RETURN 'CRITICO';
    ELSIF v_pct_baixo >= 20 THEN
        RETURN 'ALERTA';
    ELSIF v_baixo > 0 OR v_atencao > 0 THEN
        RETURN 'ATENCAO';
    ELSE
        RETURN 'SEGURO';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_stock_panel(p_company_id uuid)
RETURNS TABLE (
    company_state public.company_stock_state,
    total         int,
    criticos      int,
    baixos        int,
    atencao       int,
    normais       int
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF NOT public.fn_is_member(p_company_id) THEN
        RAISE EXCEPTION 'Sem acesso a esta empresa' USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN QUERY
    SELECT public.fn_company_stock_state(p_company_id),
           COUNT(*)::int,
           COUNT(*) FILTER (WHERE v.state = 'CRITICO')::int,
           COUNT(*) FILTER (WHERE v.state = 'BAIXO')::int,
           COUNT(*) FILTER (WHERE v.state = 'ATENCAO')::int,
           COUNT(*) FILTER (WHERE v.state = 'NORMAL')::int
      FROM public.vw_stock_situation v
     WHERE v.company_id = p_company_id;
END;
$$;


--  Configura o teto global da empresa
CREATE OR REPLACE FUNCTION public.fn_set_company_max_stock_limit(
    p_company_id uuid,
    p_limit integer
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    -- Validação: O limite não pode ser negativo
    IF p_limit IS NULL OR p_limit < 0 THEN
    RAISE EXCEPTION 'O limite máximo de estoque deve ser um número maior ou igual a zero'
        USING ERRCODE = 'check_violation';
    END IF;

    -- Validação de Permissão
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN']::public.user_role[]) THEN
        RAISE EXCEPTION 'Apenas administradores podem alterar o teto global'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF EXISTS (
    SELECT 1 FROM public.product_stock ps
    JOIN public.products p ON p.id = ps.product_id
    WHERE p.company_id = p_company_id AND ps.max_quantity > p_limit
) THEN
    RAISE EXCEPTION 'Não é possível definir o teto para %, pois existem produtos com estoque máximo superior', p_limit
        USING ERRCODE = 'check_violation';
END IF;

    UPDATE public.company SET max_stock_limit = p_limit WHERE id = p_company_id;
END;
$$;



CREATE OR REPLACE FUNCTION public.fn_get_effective_max_stock(p_product_id uuid)
RETURNS integer
LANGUAGE sql STABLE
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
    SELECT COALESCE(ps.max_quantity, c.max_stock_limit)
      FROM public.products p
      JOIN public.company c ON c.id = p.company_id
      LEFT JOIN public.product_stock ps ON ps.product_id = p.id
     WHERE p.id = p_product_id;
$$;