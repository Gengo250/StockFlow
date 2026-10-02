CREATE TYPE public.stock_state AS ENUM ('CRITICO', 'BAIXO', 'ATENCAO', 'NORMAL');
CREATE TYPE public.company_stock_state AS ENUM ('CRITICO', 'ALERTA', 'ATENCAO', 'SEGURO');


CREATE TABLE public.product_stock (
    product_id    uuid PRIMARY KEY REFERENCES public.products(id) ON DELETE CASCADE,
    min_quantity  integer NOT NULL DEFAULT 0 CHECK (min_quantity >= 0),
    updated_on    timestamptz NOT NULL DEFAULT now()
);
