CREATE TABLE sales_log (
    id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sale_id UUID NOT NULL REFERENCES public.sales(id),
    register_id UUID NOT NULL REFERENCES public.sales(created_by), 
    created_on TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
