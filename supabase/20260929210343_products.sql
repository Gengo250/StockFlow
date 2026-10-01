CREATE TABLE categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL
);

CREATE TYPE product_unit as ENUM ('UN', 'DUZ', 'CX', 'PCT', 'KG');

CREATE TABLE products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  barcode TEXT UNIQUE,
  name TEXT NOT NULL,

  buy_price NUMERIC(10,2) DEFAULT 0 CHECK ( buy_price < 0),
  sell_price NUMERIC(10,2) NOT NULL CHECK ( sell_price <= 0 ),
  unit product_unit NOT NULL,
  stock INTEGER DEFAULT 0 CHECK ( stock >= 0 ),

  item_category UUID REFERENCES categories(id) ON DELETE SET NULL,
  updated_on TIMESTAMPTZ DEFAULT NOW()
);
