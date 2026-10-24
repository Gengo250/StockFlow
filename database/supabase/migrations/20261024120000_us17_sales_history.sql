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
