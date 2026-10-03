CREATE TYPE public.unit_enum AS ENUM ('UN', 'PCT', 'DZ', 'G', 'KG', 'L', 'ML');

CREATE TABLE public.categories (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    name        text NOT NULL CHECK (btrim(name) <> ''),
    UNIQUE (company_id, name),
    UNIQUE (company_id, id)           
);

create table public.products (
  id uuid not null default gen_random_uuid (),
  barcode text null,
  name text not null,
  buy_price numeric(10, 2) null,
  sell_price numeric(10, 2) not null,
  unit integer not null,
  stock integer null default 0,
  item_category uuid null,
  created_on timestamp with time zone null default now(),
  company_id uuid null,
  active boolean not null default true,
  constraint products_pkey primary key (id),
  constraint products_barcode_key unique (barcode),
  constraint products_company_id_fkey foreign KEY (company_id) references company (id),
  constraint products_item_category_fkey foreign KEY (item_category) references categories (id) on delete set null,
  constraint products_buy_price_check check ((buy_price >= (0)::numeric)),
  constraint products_sell_price_check check ((sell_price >= (0)::numeric)),
  constraint products_stock_check check ((stock >= 0)),
  constraint products_unit_check check ((unit > 0))
) TABLESPACE pg_default;

CREATE INDEX idx_products_company ON public.products (company_id);
create trigger trg_products_create_stock
after INSERT on products for EACH row
execute FUNCTION trg_products_create_stock ();
