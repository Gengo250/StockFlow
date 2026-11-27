-- US30: devoluções ao fornecedor, identificadas por vínculo e não por novo enum.
ALTER TABLE public.products ADD CONSTRAINT uq_products_company_id_supplier_returns UNIQUE (company_id,id);

CREATE TABLE public.supplier_returns (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE RESTRICT,
    supplier_id uuid NOT NULL,
    purchase_id uuid,
    created_by uuid NOT NULL,
    created_on timestamptz NOT NULL DEFAULT now(),
    idempotency_key uuid NOT NULL,
    request_payload jsonb NOT NULL,
    UNIQUE(company_id,id),
    UNIQUE(company_id,id,supplier_id),
    UNIQUE(company_id,idempotency_key),
    FOREIGN KEY(company_id,supplier_id) REFERENCES public.suppliers(company_id,id) ON DELETE RESTRICT,
    FOREIGN KEY(company_id,purchase_id,supplier_id) REFERENCES public.purchases(company_id,id,supplier_id) ON DELETE RESTRICT
);
CREATE INDEX idx_supplier_returns_history ON public.supplier_returns(company_id,created_on DESC,id);
CREATE INDEX idx_supplier_returns_purchase ON public.supplier_returns(company_id,purchase_id) WHERE purchase_id IS NOT NULL;

CREATE TABLE public.supplier_return_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL,
    supplier_return_id uuid NOT NULL,
    position integer NOT NULL CHECK(position>0),
    product_id uuid NOT NULL,
    quantity integer NOT NULL CHECK(quantity>0 AND quantity<=1000000),
    reason text NOT NULL CHECK(length(reason)<=1000 AND reason !~ '^[[:space:]]*$'),
    UNIQUE(company_id,supplier_return_id,id),
    UNIQUE(supplier_return_id,position),
    FOREIGN KEY(company_id,supplier_return_id) REFERENCES public.supplier_returns(company_id,id) ON DELETE RESTRICT,
    FOREIGN KEY(company_id,product_id) REFERENCES public.products(company_id,id) ON DELETE RESTRICT
);
CREATE INDEX idx_supplier_return_items_header ON public.supplier_return_items(company_id,supplier_return_id);

ALTER TABLE public.stock_movements ADD COLUMN supplier_return_id uuid;
ALTER TABLE public.stock_movements ADD COLUMN supplier_return_item_id uuid;
ALTER TABLE public.stock_movements ADD CONSTRAINT fk_movement_supplier_return_item
    FOREIGN KEY(company_id,supplier_return_id,supplier_return_item_id)
    REFERENCES public.supplier_return_items(company_id,supplier_return_id,id) ON DELETE RESTRICT;
ALTER TABLE public.stock_movements ADD CONSTRAINT fk_movement_supplier_return_supplier
    FOREIGN KEY(company_id,supplier_return_id,supplier_id)
    REFERENCES public.supplier_returns(company_id,id,supplier_id) ON DELETE RESTRICT;
ALTER TABLE public.stock_movements ADD CONSTRAINT ck_movement_supplier_return
    CHECK((supplier_return_id IS NULL AND supplier_return_item_id IS NULL) OR
          (supplier_return_id IS NOT NULL AND supplier_return_item_id IS NOT NULL
           AND supplier_id IS NOT NULL AND kind='SAIDA' AND status='CONFIRMADA'
           AND confirmed_on IS NOT NULL AND sale_id IS NULL AND sale_item_id IS NULL
           AND return_id IS NULL AND cancellation_id IS NULL
           AND adjustment_reason IS NULL AND counted_balance IS NULL));
CREATE UNIQUE INDEX uq_movement_supplier_return_item ON public.stock_movements(supplier_return_item_id)
    WHERE supplier_return_item_id IS NOT NULL;
CREATE INDEX idx_movements_supplier_return ON public.stock_movements(company_id,supplier_return_id)
    WHERE supplier_return_id IS NOT NULL;
