CREATE TYPE public.user_role AS ENUM ('ADMIN', 'STOCK', 'SELLER');
CREATE TYPE public.stock_state AS ENUM ('CRITICO', 'BAIXO', 'ATENCAO', 'NORMAL');
CREATE TYPE public.company_stock_state AS ENUM ('CRITICO', 'ALERTA', 'ATENCAO', 'SEGURO');

CREATE INDEX idx_access_register_name ON public.access_register_user(name);

CREATE TABLE public.company (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    cnpj        text UNIQUE,
    active      boolean NOT NULL DEFAULT true,
    created_on  timestamptz NOT NULL DEFAULT now()
);


CREATE TABLE public.company_users (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    access_register_id uuid NOT NULL REFERENCES public.access_register(id) ON DELETE CASCADE,
    role               public.user_role NOT NULL DEFAULT 'STOCK',
    active             boolean NOT NULL DEFAULT true,
    created_on         timestamptz NOT NULL DEFAULT now(),
    updated_on         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, access_register_id)
);

CREATE TABLE public.access_register (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text UNIQUE NOT NULL, 
    pass_hash   text NOT NULL,       
    created_on  timestamptz NOT NULL DEFAULT now(),
    updated_on  timestamptz NOT NULL DEFAULT now()
);


CREATE TABLE public.product_stock (
    product_id    uuid PRIMARY KEY REFERENCES public.products(id) ON DELETE CASCADE,
    min_quantity  integer NOT NULL DEFAULT 0 CHECK (min_quantity >= 0),
    updated_on    timestamptz NOT NULL DEFAULT now()
);
