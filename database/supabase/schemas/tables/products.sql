CREATE TABLE categories (
  id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE
);

CREATE TYPE unit_enum AS ENUM ('UN', 'DZ', 'PCT', 'CX', 'MG', 'KG', 'ML', 'L');

CREATE TABLE products (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  barcode       TEXT UNIQUE,
  name          TEXT NOT NULL,
  buy_price     NUMERIC(10,2) CHECK (buy_price >= 0),
  sell_price    NUMERIC(10,2) NOT NULL CHECK (sell_price >= 0),
  unit          unit_enum NOT NULL DEFAULT 'UN',
  stock         INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
  item_category UUID REFERENCES categories(id) ON DELETE SET NULL,
  created_on    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX products_item_category_idx ON products(item_category);
