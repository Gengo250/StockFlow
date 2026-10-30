-- US17/US20: não desfazer novamente uma venda já restituída pela US20.
-- Guarda na transição de sales, sem substituir as RPCs existentes da US17.
-- Uma exceção desfaz também movimentos que a RPC legada já tenha alterado
-- na mesma transação. Ambas as operações serializam a mesma linha de sales.
CREATE OR REPLACE FUNCTION public.trg_guard_sale_after_return()
RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    -- DEFINER é necessário para não depender da visibilidade de returns por RLS.
    -- Não expõe leitura ou escrita como RPC: só valida a própria venda alterada.
    IF EXISTS (
        SELECT 1 FROM public.returns r
         WHERE r.company_id = OLD.company_id AND r.sale_id = OLD.id
           AND r.status = 'COMPLETED'
    ) THEN
        RAISE EXCEPTION 'Venda com devolução registrada; utilize o fluxo de devolução por itens'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.trg_guard_sale_after_return()
    FROM PUBLIC, anon, authenticated, app_backend;

DROP TRIGGER IF EXISTS trg_guard_sale_after_return ON public.sales;
CREATE TRIGGER trg_guard_sale_after_return
    BEFORE UPDATE OF status ON public.sales
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status
          AND NEW.status::text IN ('CANCELADA', 'DEVOLVIDA'))
    EXECUTE FUNCTION public.trg_guard_sale_after_return();
