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
