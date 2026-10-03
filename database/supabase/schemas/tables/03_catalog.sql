-- Catálogo multi-tenant. Depende de company (01_identity).

CREATE TYPE public.unit_enum AS ENUM ('UN', 'PCT', 'DZ', 'G', 'KG', 'L', 'ML');

CREATE TABLE public.categories (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    name        text NOT NULL CHECK (btrim(name) <> ''),
    -- Escopado por empresa: duas empresas podem ter "Periféricos".
    UNIQUE (company_id, name),
    -- Alvo da FK composta de products, que garante que produto e categoria
    -- pertencem à mesma empresa.
    UNIQUE (company_id, id)
);

CREATE TABLE public.products (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    barcode        text,
    name           text NOT NULL CHECK (btrim(name) <> ''),
    buy_price      numeric(10,2) CHECK (buy_price >= 0),
    sell_price     numeric(10,2) NOT NULL CHECK (sell_price >= 0),
    unit           public.unit_enum NOT NULL DEFAULT 'UN',
    stock          integer NOT NULL DEFAULT 0 CHECK (stock >= 0),
    item_category  uuid,
    active         boolean NOT NULL DEFAULT true,
    created_on     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, barcode),
    FOREIGN KEY (company_id, item_category)
        REFERENCES public.categories (company_id, id)
        ON DELETE SET NULL (item_category)
);
CREATE INDEX idx_products_company ON public.products (company_id);
