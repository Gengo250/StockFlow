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


-- Índices únicos tornam a exclusividade atômica, inclusive em concorrência.
CREATE UNIQUE INDEX IF NOT EXISTS register_log_one_open_operator ON public.register_log(operator_id) WHERE status='OPEN';
CREATE UNIQUE INDEX IF NOT EXISTS register_log_one_open_terminal ON public.register_log(register_id) WHERE status='OPEN';
ALTER TABLE public.register_log ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.register_log FROM anon, authenticated;
