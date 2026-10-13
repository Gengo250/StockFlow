ALTER TABLE public.products
ADD COLUMN updated_on TIMESTAMPTZ NOT NULL DEFAULT NOW();


ALTER TABLE public.products
ADD COLUMN last_updated_by UUID;
