CREATE TYPE public.payment_method AS ENUM (
  'CASH',
  'DEBIT',
  'CREDIT',
  'PIX',
  'VOUCHER',
  'OTHER'
);

ALTER TABLE public.sales 
ADD COLUMN IF NOT EXISTS payment_method public.payment_method NOT NULL DEFAULT 'CASH';

ALTER TABLE public.sales 
ADD COLUMN IF NOT EXISTS discount numeric(10,2) NOT NULL DEFAULT 0.00 CHECK (discount >= 0);
