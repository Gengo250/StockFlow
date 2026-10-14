CREATE TABLE stock_log (
    id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    barcode VARCHAR NOT NULL,
    quantity_changed INTEGER NOT NULL,
    old_stock INTEGER NOT NULL,
    new_stock INTEGER NOT NULL,
    created_on TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
