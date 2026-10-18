-- Fecha a reconciliação do histórico remoto com a fonte declarativa.
-- Não altera vendas nem saldos. Os índices abaixo são duplicatas dos
-- índices idx_*_sale/company criados pela migration de checkout.
--
-- A transação é aberta pelo próprio arquivo, como na US09/US10: `supabase db
-- push` manda cada comando separadamente, em autocommit, e sem o BEGIN uma
-- falha no meio deixaria metade da auditoria de preços de pé — tabela criada
-- sem a policy que restringe a leitura, por exemplo.

BEGIN;

DROP INDEX IF EXISTS public.idx_sale_items_sale_id;
DROP INDEX IF EXISTS public.idx_sale_items_company_id;
DROP INDEX IF EXISTS public.idx_stock_movements_sale_id;

-- Entrada antiga sem checagem de papel e com autoria fornecida pelo cliente.
-- A aplicação usa fn_register_movement/fn_register_supplier_movement.
DROP FUNCTION IF EXISTS public.fn_register_stock_entry(uuid,uuid,numeric,uuid,uuid,text);

-- Preserva a auditoria de preços introduzida pelo histórico remoto.
CREATE TABLE IF NOT EXISTS public.price_edit_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    updated_by uuid,
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    last_updated_on timestamptz NOT NULL DEFAULT now(),
    old_price numeric NOT NULL,
    new_price numeric NOT NULL,
    product_id uuid NOT NULL REFERENCES public.products(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_price_edit_log_product_id ON public.price_edit_log(product_id);
CREATE INDEX IF NOT EXISTS idx_price_edit_log_company_id ON public.price_edit_log(company_id);

CREATE OR REPLACE FUNCTION public.trg_log_price_edit()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF OLD.sell_price IS DISTINCT FROM NEW.sell_price THEN
        INSERT INTO public.price_edit_log (
            updated_by, company_id, old_price, new_price, product_id
        ) VALUES (
            public.fn_current_user_id(), NEW.company_id,
            OLD.sell_price, NEW.sell_price, NEW.id
        );
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_price_edit_log ON public.products;
CREATE TRIGGER trg_price_edit_log
    AFTER UPDATE OF sell_price ON public.products
    FOR EACH ROW EXECUTE FUNCTION public.trg_log_price_edit();

ALTER TABLE public.price_edit_log ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.price_edit_log FROM PUBLIC, anon, authenticated, app_backend;
GRANT SELECT ON public.price_edit_log TO app_backend, authenticated;
DROP POLICY IF EXISTS price_edit_log_select ON public.price_edit_log;
CREATE POLICY price_edit_log_select ON public.price_edit_log
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[]));
REVOKE ALL ON FUNCTION public.trg_log_price_edit()
  FROM PUBLIC, anon, authenticated, app_backend;
NOTIFY pgrst, 'reload schema';

COMMIT;
