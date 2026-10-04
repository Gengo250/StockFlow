-- Fornecedores e relações opcionais com catálogo e entradas de estoque.

CREATE TABLE public.suppliers (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    name        text NOT NULL CHECK (btrim(name) <> ''),
    document    text,
    phone       text NOT NULL DEFAULT '',
    email       text NOT NULL DEFAULT '',
    address     text NOT NULL DEFAULT '',
    active      boolean NOT NULL DEFAULT true,
    created_on  timestamptz NOT NULL DEFAULT now(),
    updated_on  timestamptz NOT NULL DEFAULT now(),
    CHECK (document IS NULL OR
           (document <> '' AND public.fn_valid_br_document(document))),
    CHECK (email = '' OR email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
    CHECK (phone = '' OR (
           phone ~ '^[+0-9().[:space:]-]+$' AND
           length(regexp_replace(phone, '\D', '', 'g')) IN (10, 11))),
    UNIQUE (company_id, id)
);

CREATE UNIQUE INDEX uq_suppliers_company_document
    ON public.suppliers (company_id, document)
    WHERE document IS NOT NULL AND document <> '';
CREATE INDEX idx_suppliers_company_name
    ON public.suppliers (company_id, lower(name));

ALTER TABLE public.products
    ADD COLUMN supplier_id uuid;
ALTER TABLE public.products
    ADD CONSTRAINT fk_products_supplier_company
    FOREIGN KEY (company_id, supplier_id)
    REFERENCES public.suppliers (company_id, id)
    ON DELETE RESTRICT;

ALTER TABLE public.stock_movements
    ADD COLUMN supplier_id uuid;
ALTER TABLE public.stock_movements
    ADD CONSTRAINT fk_stock_movements_supplier_company
    FOREIGN KEY (company_id, supplier_id)
    REFERENCES public.suppliers (company_id, id)
    ON DELETE RESTRICT;
CREATE INDEX idx_stock_movements_supplier
    ON public.stock_movements (supplier_id)
    WHERE supplier_id IS NOT NULL;
