-- ------------------------------------------------------------
-- Itens de devolução (detalhes por linha)
-- ------------------------------------------------------------

CREATE TABLE public.return_items (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Repetidos para integridade multiempresa e leitura sob RLS.
    company_id    uuid NOT NULL,
    sale_id       uuid NOT NULL,
    return_id     uuid NOT NULL,
    -- Produto, nome e código são obtidos pelo item original; não duplicar product_id.
    sale_item_id  uuid NOT NULL,
    quantity      integer NOT NULL CHECK (quantity > 0),
    unit_price    numeric(10,2) NOT NULL CHECK (unit_price >= 0),
    -- Valor monetário atribuído a esta devolução, não percentual (sales.discount).
    discount      numeric(12,2) NOT NULL DEFAULT 0 CHECK (discount >= 0),
    subtotal      numeric(12,2) NOT NULL CHECK (subtotal >= 0),
    created_on    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_return_items_return FOREIGN KEY (company_id, sale_id, return_id)
        REFERENCES public.returns (company_id, sale_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_return_items_sale_item FOREIGN KEY (company_id, sale_id, sale_item_id)
        REFERENCES public.sale_items (company_id, sale_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_return_items_return_sale_item UNIQUE (return_id, sale_item_id),
    CONSTRAINT ck_return_items_discount CHECK (discount <= quantity::numeric * unit_price),
    CONSTRAINT ck_return_items_subtotal CHECK (subtotal = quantity::numeric * unit_price - discount)
);

CREATE INDEX idx_return_items_return ON public.return_items (return_id);
CREATE INDEX idx_return_items_sale_item ON public.return_items (sale_item_id);
CREATE INDEX idx_return_items_company ON public.return_items (company_id);

-- Só agora returns/return_items existem na ordem declarativa.
-- ENTRADA + vínculo estruturado identifica a devolução, sem ampliar movement_kind.
ALTER TABLE public.stock_movements
    ADD COLUMN return_id uuid,
    ADD CONSTRAINT fk_stock_movements_return FOREIGN KEY (company_id, sale_id, return_id)
        REFERENCES public.returns (company_id, sale_id, id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_stock_movements_return_item FOREIGN KEY (return_id, sale_item_id)
        REFERENCES public.return_items (return_id, sale_item_id) ON DELETE RESTRICT,
    ADD CONSTRAINT ck_stock_movements_return CHECK (
        return_id IS NULL OR (
            sale_id IS NOT NULL AND sale_item_id IS NOT NULL
            AND kind = 'ENTRADA' AND status = 'CONFIRMADA'
            AND created_by IS NOT NULL AND confirmed_on IS NOT NULL
            AND adjustment_reason IS NULL AND counted_balance IS NULL
        )
    );
CREATE UNIQUE INDEX uq_stock_movements_return_item
    ON public.stock_movements (return_id, sale_item_id) WHERE return_id IS NOT NULL;
