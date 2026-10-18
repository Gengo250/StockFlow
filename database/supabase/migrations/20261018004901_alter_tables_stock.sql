ALTER TABLE public.product_stock
ADD COLUMN IF NOT EXISTS max_quantity integer;

ALTER TABLE public.stock_movements
ADD COLUMN IF NOT EXISTS sale_id uuid REFERENCES public.sales(id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS sale_item_id uuid REFERENCES public.sale_items(id) ON DELETE SET NULL;


ALTER TABLE public.company
ADD COLUMN IF NOT EXISTS max_stock_limit integer NOT NULL DEFAULT 10000 CHECK (max_stock_limit >= 0);


