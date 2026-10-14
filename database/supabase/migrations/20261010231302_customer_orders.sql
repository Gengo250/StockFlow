DROP TABLE IF EXISTS public.sales CASCADE;
CREATE TYPE public.sale_status AS ENUM ('PENDING', 'COMPLETE');
CREATE TABLE public.sales (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    client_id         uuid,
    customer_name     text DEFAULT 'Consumidor',
    customer_document text,
    total             numeric(10,2) NOT NULL DEFAULT 0.00 CHECK (total >= 0),
    status            sale_status NOT NULL DEFAULT 'PENDING',
    created_by        uuid NOT NULL REFERENCES public.register(id),
    created_on        timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, client_id)
          REFERENCES public.clients (company_id, id) ON DELETE SET NULL,
    UNIQUE (company_id, id)
);
CREATE INDEX idx_sales_company_created
  ON public.sales (company_id, created_on DESC);
CREATE TABLE public.sale_items(
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        uuid NOT NULL,
    sale_id           uuid NOT NULL,
    product_id        uuid,
    product_name      text NOT NULL,
    product_code      text NOT NULL,
    quantity          numeric(10,3) NOT NULL CHECK (quantity > 0),
    unit_price        numeric(10,2) NOT NULL CHECK (unit_price >= 0),
    subtotal          numeric(10,2) NOT NULL GENERATED ALWAYS AS (quantity * unit_price) STORED,
    created_on        timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE CASCADE,
    FOREIGN KEY (product_id)
        REFERENCES public.products (id) ON DELETE SET NULL
);
CREATE INDEX idx_sale_items_sale_id ON public.sale_items (sale_id);
CREATE INDEX idx_sale_items_company_id ON public.sale_items (company_id);
