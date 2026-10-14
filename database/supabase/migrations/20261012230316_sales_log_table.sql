CREATE TABLE IF NOT EXISTS public.sales_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sale_id uuid REFERENCES public.sales(id) ON DELETE CASCADE,
    created_by uuid,
    logged_on timestamp with time zone DEFAULT now()
);
