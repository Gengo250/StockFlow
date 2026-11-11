-- Compras em rascunho e itens recebidos. O estoque só muda quando a compra
-- inteira é recebida e suas entradas confirmadas são gravadas no ledger.

CREATE TYPE public.purchase_status AS ENUM ('RASCUNHO', 'RECEBIDA');

CREATE TABLE public.purchases (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    supplier_id uuid NOT NULL,
    status      public.purchase_status NOT NULL DEFAULT 'RASCUNHO',
    created_by  uuid,
    created_on  timestamptz NOT NULL DEFAULT now(),
    received_on timestamptz,
    UNIQUE (company_id, id),
    UNIQUE (company_id, id, supplier_id),
    FOREIGN KEY (company_id, supplier_id)
        REFERENCES public.suppliers (company_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_purchases_received_on CHECK (
        (status = 'RASCUNHO' AND received_on IS NULL)
        OR (status = 'RECEBIDA' AND received_on IS NOT NULL)
    )
);

CREATE INDEX idx_purchases_company_created
    ON public.purchases (company_id, created_on DESC);

CREATE TABLE public.purchase_items (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL,
    purchase_id uuid NOT NULL,
    product_id  uuid NOT NULL REFERENCES public.products (id) ON DELETE RESTRICT,
    quantity    integer NOT NULL CHECK (quantity > 0),
    created_on  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, purchase_id, id),
    FOREIGN KEY (company_id, purchase_id)
        REFERENCES public.purchases (company_id, id) ON DELETE CASCADE
);

CREATE INDEX idx_purchase_items_purchase
    ON public.purchase_items (company_id, purchase_id, id);

ALTER TABLE public.stock_movements
    ADD COLUMN purchase_id uuid;
ALTER TABLE public.stock_movements
    ADD CONSTRAINT fk_stock_movements_purchase_supplier
    FOREIGN KEY (company_id, purchase_id, supplier_id)
    REFERENCES public.purchases (company_id, id, supplier_id)
    ON DELETE RESTRICT;
CREATE INDEX idx_stock_movements_purchase
    ON public.stock_movements (company_id, purchase_id)
    WHERE purchase_id IS NOT NULL;
