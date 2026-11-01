-- ============================================================================
-- 1. TABELA REGISTER_LOG (Sessões de Caixa)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.register_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    register_id uuid NOT NULL REFERENCES public.register(id) ON DELETE CASCADE,
    operator_id uuid NOT NULL,
    session_id uuid REFERENCES public.access_register(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
    initial_balance numeric(10, 2) NOT NULL DEFAULT 0.00 CHECK (initial_balance >= 0),
    opened_at timestamp with time zone NOT NULL DEFAULT now(),
    closed_at timestamp with time zone,
    
    -- Totais Calculados pelo Sistema (Esperados das vendas CONCLUIDA)
    total_dinheiro numeric(10, 2) NOT NULL DEFAULT 0.00,
    total_debito numeric(10, 2) NOT NULL DEFAULT 0.00,
    total_credito numeric(10, 2) NOT NULL DEFAULT 0.00,
    total_pix numeric(10, 2) NOT NULL DEFAULT 0.00,
    total_vale numeric(10, 2) NOT NULL DEFAULT 0.00,
    total_outro numeric(10, 2) NOT NULL DEFAULT 0.00,
    total_sales numeric(10, 2) NOT NULL DEFAULT 0.00,
    
    -- Valores Declarados / Contados pelo Operador no Fechamento
    declared_dinheiro numeric(10, 2) DEFAULT 0.00,
    declared_debito numeric(10, 2) DEFAULT 0.00,
    declared_credito numeric(10, 2) DEFAULT 0.00,
    declared_pix numeric(10, 2) DEFAULT 0.00,
    declared_vale numeric(10, 2) DEFAULT 0.00,
    declared_outro numeric(10, 2) DEFAULT 0.00,
    total_declared numeric(10, 2) DEFAULT 0.00,
    
    -- Diferença e Justificativa Obrigatória em Divergência
    difference numeric(10, 2) DEFAULT 0.00,
    justification text,
    
    CONSTRAINT chk_justification_when_difference CHECK (
        status = 'OPEN' OR (difference = 0.00) OR (justification IS NOT NULL AND trim(justification) <> '')
    )
);

CREATE INDEX IF NOT EXISTS idx_register_log_company ON public.register_log(company_id);
CREATE INDEX IF NOT EXISTS idx_register_log_operator_open ON public.register_log(operator_id) WHERE status = 'OPEN';
CREATE INDEX IF NOT EXISTS idx_register_log_register_open ON public.register_log(register_id) WHERE status = 'OPEN';

-- ============================================================================
-- 2. ALTERAÇÕES NA TABELA SALES
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'sales' AND column_name = 'register_log_id'
    ) THEN
        ALTER TABLE public.sales ADD COLUMN register_log_id uuid REFERENCES public.register_log(id) ON DELETE RESTRICT;
        CREATE INDEX idx_sales_register_log ON public.sales(register_log_id);
    END IF;
END $$;

-- ============================================================================
-- 3. PROCEDURES, FUNCTIONS E TRIGGERS
-- ============================================================================

-- A. Validação de abertura: impede operador com caixa aberto e inicializa o caixa
CREATE OR REPLACE FUNCTION public.fn_open_register_session(
    p_company_id uuid,
    p_register_id uuid,
    p_operator_id uuid,
    p_session_id uuid,
    p_initial_balance numeric
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_new_log_id uuid;
BEGIN
    IF p_initial_balance < 0 THEN
        RAISE EXCEPTION 'O saldo inicial não pode ser negativo.';
    END IF;

    -- Impede operador de ter mais de uma sessão aberta simultaneamente
    IF EXISTS (
        SELECT 1 FROM public.register_log 
        WHERE operator_id = p_operator_id AND status = 'OPEN'
    ) THEN
        RAISE EXCEPTION 'Operador já possui uma sessão de caixa aberta simultaneamente.';
    END IF;

    -- Impede o mesmo terminal de caixa de ser aberto mais de uma vez
    IF EXISTS (
        SELECT 1 FROM public.register_log 
        WHERE register_id = p_register_id AND status = 'OPEN'
    ) THEN
        RAISE EXCEPTION 'Este caixa físico já se encontra com uma sessão aberta.';
    END IF;

    INSERT INTO public.register_log (
        company_id,
        register_id,
        operator_id,
        session_id,
        initial_balance,
        status,
        opened_at
    ) VALUES (
        p_company_id,
        p_register_id,
        p_operator_id,
        p_session_id,
        p_initial_balance,
        'OPEN',
        now()
    ) RETURNING id INTO v_new_log_id;

    -- Atualiza o saldo (change) no registro do caixa
    UPDATE public.register
    SET change = p_initial_balance,
        logged_on = now(),
        session_id = p_session_id
    WHERE id = p_register_id;

    RETURN v_new_log_id;
END;
$$;

-- B. Trigger em sales: Valida se a venda está atrelada a um caixa aberto
CREATE OR REPLACE FUNCTION public.trg_guard_sale_open_register()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_register_status text;
BEGIN
    IF NEW.register_log_id IS NULL THEN
        RAISE EXCEPTION 'Venda deve estar associada a uma sessão de caixa aberta.';
    END IF;

    SELECT status INTO v_register_status
    FROM public.register_log
    WHERE id = NEW.register_log_id;

    IF v_register_status IS NULL THEN
        RAISE EXCEPTION 'Sessão de caixa informada não existe.';
    END IF;

    IF v_register_status = 'CLOSED' THEN
        RAISE EXCEPTION 'Não é permitido registrar ou alterar vendas em um caixa fechado.';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_validate_sale_open_register ON public.sales;
CREATE TRIGGER trg_validate_sale_open_register
BEFORE INSERT OR UPDATE ON public.sales
FOR EACH ROW
EXECUTE FUNCTION public.trg_guard_sale_open_register();

-- C. Fechamento de caixa: compara contagens, calcula diferenças e encerra a sessão
CREATE OR REPLACE FUNCTION public.fn_close_register_session(
    p_register_log_id uuid,
    p_declared_dinheiro numeric DEFAULT 0.00,
    p_declared_debito numeric DEFAULT 0.00,
    p_declared_credito numeric DEFAULT 0.00,
    p_declared_pix numeric DEFAULT 0.00,
    p_declared_vale numeric DEFAULT 0.00,
    p_declared_outro numeric DEFAULT 0.00,
    p_justification text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_log public.register_log%ROWTYPE;
    v_dinheiro numeric(10,2) := 0.00;
    v_debito numeric(10,2) := 0.00;
    v_credito numeric(10,2) := 0.00;
    v_pix numeric(10,2) := 0.00;
    v_vale numeric(10,2) := 0.00;
    v_outro numeric(10,2) := 0.00;
    v_total_sales numeric(10,2) := 0.00;
    v_total_declared numeric(10,2) := 0.00;
    v_total_expected numeric(10,2) := 0.00;
    v_diff numeric(10,2) := 0.00;
BEGIN
    SELECT * INTO v_log 
    FROM public.register_log 
    WHERE id = p_register_log_id 
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Sessão de caixa não encontrada.';
    END IF;

    IF v_log.status = 'CLOSED' THEN
        RAISE EXCEPTION 'Esta sessão de caixa já se encontra fechada.';
    END IF;

    -- Agregação dos valores das vendas CONCLUIDAS no caixa
    SELECT 
        COALESCE(SUM(CASE WHEN payment_method = 'DINHEIRO' THEN total ELSE 0 END), 0.00),
        COALESCE(SUM(CASE WHEN payment_method = 'DEBITO' THEN total ELSE 0 END), 0.00),
        COALESCE(SUM(CASE WHEN payment_method = 'CREDITO' THEN total ELSE 0 END), 0.00),
        COALESCE(SUM(CASE WHEN payment_method = 'PIX' THEN total ELSE 0 END), 0.00),
        COALESCE(SUM(CASE WHEN payment_method = 'VALE' THEN total ELSE 0 END), 0.00),
        COALESCE(SUM(CASE WHEN payment_method = 'OUTRO' THEN total ELSE 0 END), 0.00)
    INTO v_dinheiro, v_debito, v_credito, v_pix, v_vale, v_outro
    FROM public.sales
    WHERE register_log_id = p_register_log_id 
      AND status = 'CONCLUIDA'::sale_status;

    v_total_sales := v_dinheiro + v_debito + v_credito + v_pix + v_vale + v_outro;
    v_total_expected := v_log.initial_balance + v_total_sales;
    v_total_declared := COALESCE(p_declared_dinheiro, 0) + 
                        COALESCE(p_declared_debito, 0) + 
                        COALESCE(p_declared_credito, 0) + 
                        COALESCE(p_declared_pix, 0) + 
                        COALESCE(p_declared_vale, 0) + 
                        COALESCE(p_declared_outro, 0);

    v_diff := v_total_declared - v_total_expected;

    IF v_diff <> 0.00 AND (p_justification IS NULL OR trim(p_justification) = '') THEN
        RAISE EXCEPTION 'Divergência de valores detectada (Diferença: %). É obrigatório informar uma justificativa.', v_diff;
    END IF;

    UPDATE public.register_log
    SET status = 'CLOSED',
        closed_at = now(),
        total_dinheiro = v_dinheiro,
        total_debito = v_debito,
        total_credito = v_credito,
        total_pix = v_pix,
        total_vale = v_vale,
        total_outro = v_outro,
        total_sales = v_total_sales,
        declared_dinheiro = p_declared_dinheiro,
        declared_debito = p_declared_debito,
        declared_credito = p_declared_credito,
        declared_pix = p_declared_pix,
        declared_vale = p_declared_vale,
        declared_outro = p_declared_outro,
        total_declared = v_total_declared,
        difference = v_diff,
        justification = p_justification
    WHERE id = p_register_log_id;

    -- Zera a sessão ativa do terminal
    UPDATE public.register
    SET session_id = NULL
    WHERE id = v_log.register_id;

    RETURN jsonb_build_object(
        'register_log_id', p_register_log_id,
        'status', 'CLOSED',
        'initial_balance', v_log.initial_balance,
        'total_sales', v_total_sales,
        'total_expected', v_total_expected,
        'total_declared', v_total_declared,
        'difference', v_diff
    );
END;
$$;
